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
[pendiente] build_index(): embeddings (models.embeddings) + BM25 → index/ (numpy + json; sin base de datos).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

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


def build_index(chunks: list[Chunk] | None = None) -> None:
    raise NotImplementedError("Índice pendiente: embeddings + BM25 sobre build_chunks(), guardado en index/.")
