"""
AGENTE 3 · Preguntas de empleados (RAG) — paso 1: el índice.

Qué se indexa (por orden de valor):
  1. las secciones de los `00_CONTEXTO.md` (un fragmento por sección: ya están escritas para responder preguntas);
  2. los documentos vigentes de texto citados por ellos: README de sección, CLAUDE.md, instrucciones de
     Gestión Clientes, LEEME, fichas, contratos, correos .eml, informes HTML, PDF corporativos;
  3. (opcional) tesis y anexos largos.
Qué NO se indexa: lo que el manifiesto marca como archivo o duplicado, binarios (xlsx, parquet) y el IC Committee
(se puede activar después).

Cada fragmento (Chunk) lleva metadatos del manifiesto: carpeta, sección, tipo y ruta → permiten filtrar ANTES de
buscar («¿quién lleva HY?» solo necesita mirar en 14. y en 01.) y citar la fuente en la respuesta.

[hecho]     build_chunks(): trocea contextos por sección y el resto por bloques de ~chunk_tokens.
[hecho]     build_index() / search(): BM25 léxico sobre los fragmentos, guardado en index/chunks.jsonl.
[pendiente] embeddings (models.embeddings) y fusión con BM25 por rangos (RRF) → búsqueda híbrida.

Cómo funciona BM25, en una frase: un fragmento puntúa alto si contiene las palabras de la pregunta que son RARAS
en el corpus («Luxemburgo», «privatedesk», «NextPortfolio»), y apenas suma por las comunes («cartera», «sección»).
Además se normaliza por longitud, para que un documento largo no gane solo por tener más palabras.
Por eso es tan bueno con nombres propios, correos y siglas, justo lo que más preguntan los empleados.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache

from ...config import get_settings
from ...corpus import extract, load_contexts, load_manifest, select

# Extensiones que se indexan en el paso 2 (los contextos van aparte)
INDEX_EXTS = (".md", ".txt", ".eml", ".html", ".pdf")
SKIP_FOLDERS = ("60. Proyectos",)   # IC Committee: cientos de JSON de ejecuciones; no responde preguntas de empleados


@dataclass
class Chunk:
    id: str
    text: str
    source: str          # ruta relativa del fichero
    folder: str          # carpeta de primer nivel
    section: str         # sección del corpus (Alpha, Gestión de clientes…)
    heading: str         # «§2 Responsables» en contextos; «p. 4» en PDF; título en el resto
    kind: str            # tipo de documento según el manifiesto

    def to_dict(self) -> dict:
        return asdict(self)


def _split(text: str, max_words: int) -> list[str]:
    """Trocea por párrafos sin pasar de max_words (≈ tokens × 0,75). Un párrafo enorme se corta por frases."""
    paras, out, cur = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()], [], []
    count = 0
    for p in paras:
        w = len(p.split())
        if count + w > max_words and cur:
            out.append("\n\n".join(cur)); cur, count = [], 0
        if w > max_words:
            sentences = re.split(r"(?<=[.!?])\s+", p)
            for sen in sentences:
                if count + len(sen.split()) > max_words and cur:
                    out.append("\n\n".join(cur)); cur, count = [], 0
                cur.append(sen); count += len(sen.split())
            continue
        cur.append(p); count += w
    if cur:
        out.append("\n\n".join(cur))
    return out


def build_chunks(include_documents: bool = True) -> list[Chunk]:
    s = get_settings()
    max_words = int(s.chunk_tokens * 0.75)
    files = load_manifest()
    meta = {f.rel: f for f in files}
    chunks: list[Chunk] = []
    # 1) contextos: un fragmento por sección (troceado solo si la sección es muy larga)
    context_rels = set()
    for doc in load_contexts():
        context_rels.add(doc.rel)
        f = meta.get(doc.rel)
        for sec in doc.sections:
            for k, part in enumerate(_split(sec.text, max_words)):
                chunks.append(Chunk(id=f"{doc.rel}#{sec.number}.{k}", text=f"{doc.title} — {sec.title}\n\n{part}",
                                    source=doc.rel, folder=sec.folder.split("/")[0], section=f.section if f else "",
                                    heading=f"§{sec.number} {sec.title}", kind="contexto"))
    if not include_documents:
        return chunks
    # 2) documentos vigentes de texto
    for f in select(files, exts=INDEX_EXTS):
        if f.rel in context_rels or f.folder.startswith(SKIP_FOLDERS) or not f.path.exists():
            continue
        for page in extract(f.path, f.rel):
            for k, part in enumerate(_split(page.text, max_words)):
                if len(part.split()) < 8:
                    continue
                heading = f"p. {page.page}" if f.ext == ".pdf" else f.path.stem
                chunks.append(Chunk(id=f"{f.rel}#{page.page}.{k}", text=part, source=f.rel, folder=f.folder,
                                    section=f.section, heading=heading, kind=f.kind))
    return chunks


# ----------------------------------------------------------------------------------------------------------------
# Normalización del texto para BM25
# ----------------------------------------------------------------------------------------------------------------
# Palabras vacías: aparecen en todos los fragmentos y no distinguen ninguno. Se quitan antes de puntuar.
STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun bajo bien cada como con cual cuales cuando
cuanto de del desde donde dos el ella ellas ello ellos en entre era es esa esas ese eso esos esta estan estar este
esto estos fue ha hace hacia han hasta hay la las le les lo los mas me mi mientras muy nada ni no nos o otra otras
otro otros para pero poco por porque que quien quienes se sea segun ser si sin sino sobre son su sus tambien tanto
te tiene tienen todo todos tras tu un una unas uno unos y ya the of and to in for is on
""".split())

_TOKEN = re.compile(r"[a-z0-9]+(?:[@._-][a-z0-9]+)*")


@lru_cache(maxsize=1)
def _stemmer():
    import snowballstemmer

    return snowballstemmer.stemmer("spanish")


def _strip_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """
    Texto → lista de términos comparables.
      «Operativa de Luxemburgo» → ['operat', 'luxemburg']
      «privatedesk@andbank.lu»  → ['privatedesk@andbank.lu', 'privatedesk', 'andbank', 'lu']
    Minúsculas y sin tildes; los correos y rutas se guardan enteros Y por partes (así se encuentran tanto si se
    pregunta por el correo completo como por «privatedesk»); el resto de palabras, reducidas a su raíz.
    """
    st = _stemmer()
    out: list[str] = []
    for tok in _TOKEN.findall(_strip_accents(text.lower())):
        if re.search(r"[@._-]", tok):
            out.append(tok)
            out.extend(p for p in re.split(r"[@._-]", tok) if len(p) > 1 and p not in STOPWORDS)
        elif tok not in STOPWORDS and (len(tok) > 1 or tok.isdigit()):
            out.append(st.stemWord(tok) if tok.isalpha() else tok)
    return out


# ----------------------------------------------------------------------------------------------------------------
# BM25
# ----------------------------------------------------------------------------------------------------------------
class BM25:
    """
    BM25 clásico (Okapi). Para cada término t de la pregunta y cada fragmento d:

        idf(t) · f(t,d)·(k1+1) / ( f(t,d) + k1·(1 − b + b·|d|/media) )

      idf(t)  premia los términos raros en el corpus;  f(t,d) = veces que t aparece en d;
      k1      satura la repetición (repetir 10 veces una palabra no vale 10 veces más);
      b       penaliza los fragmentos largos frente a la media.
    """

    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.len = [len(d) for d in docs]
        self.avg = sum(self.len) / max(1, len(docs))
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in Counter(d).items():
                self.postings[t].append((i, f))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def scores(self, query: list[str]) -> dict[int, float]:
        out: dict[int, float] = defaultdict(float)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, f in self.postings[t]:
                out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return out


# ----------------------------------------------------------------------------------------------------------------
# Índice en disco y búsqueda
# ----------------------------------------------------------------------------------------------------------------
CONTEXT_BOOST = 1.15   # los contextos están escritos para responder: a igualdad de puntuación, ganan ellos


def _index_file():
    return get_settings().index_dir / "chunks.jsonl"


def build_index(chunks: list[Chunk] | None = None, log=print) -> int:
    """Trocea el corpus y guarda los fragmentos en index/chunks.jsonl. Se rehace cuando cambia la carpeta de datos."""
    chunks = chunks if chunks is not None else build_chunks()
    path = _index_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in chunks:   # se guardan también los términos ya normalizados: cargar el índice pasa de ~7 s a ~1 s
            fh.write(json.dumps({**c.to_dict(), "terms": _terms(c)}, ensure_ascii=False) + "\n")
    _load.cache_clear()
    log(f"índice: {len(chunks)} fragmentos → {path}")
    return len(chunks)


def _terms(c: Chunk) -> list[str]:
    # se indexa también la ruta y el encabezado: «02_reglas-operativas» ya dice de qué va el fragmento
    return tokenize(f"{c.heading} {c.source} {c.text}")


@lru_cache(maxsize=1)
def _load() -> tuple[list[Chunk], BM25]:
    path = _index_file()
    if not path.exists():
        build_index()
    chunks, terms = [], []
    for line in path.open(encoding="utf-8"):
        d = json.loads(line)
        t = d.pop("terms", None)
        c = Chunk(**d)
        chunks.append(c)
        terms.append(t if t is not None else _terms(c))
    return chunks, BM25(terms)


def search(query: str, k: int | None = None) -> list[tuple[float, Chunk]]:
    """Los k fragmentos más relevantes para la pregunta, de mayor a menor puntuación."""
    k = k or get_settings().top_k
    chunks, bm25 = _load()
    sc = bm25.scores(tokenize(query))
    ranked = sorted(((v * (CONTEXT_BOOST if chunks[i].kind == "contexto" else 1.0), i) for i, v in sc.items()),
                    reverse=True)
    return [(round(v, 3), chunks[i]) for v, i in ranked[:k]]
