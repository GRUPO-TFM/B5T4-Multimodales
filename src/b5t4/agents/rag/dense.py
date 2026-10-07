"""
AGENTE 3 · búsqueda semántica (densa) con EmbeddingGemma 2, sobre TEXTO e IMÁGENES de página.

Qué se indexa:
  1. los mismos fragmentos de texto que BM25 (index/chunks.jsonl, generado por `b5t4 rag index`);
  2. cada página de los PDF de la Opinión Corporativa como IMAGEN (corpus.pdf_page_images). Si una página gana
     por lo que se ve en ella (un gráfico, una tabla de recomendaciones), al LLM se le pasa el texto de esa
     página y se cita como «p. N (imagen)». Así una pregunta de texto o de voz encuentra contenido visual.

Dónde se guarda: index/dense_<modelo>_<dim>/ → vectors.npy (n × d, normalizados) + meta.jsonl (un fragmento por fila).
Se construye una vez (`uv run python scripts/rag_dense_index.py`, minutos en CPU) y se repite si cambian los datos.
La búsqueda es un producto escalar con numpy: con ~3.000 vectores de 256 dimensiones tarda milisegundos y no
hace falta una base vectorial (Qdrant u otra queda como opción si el corpus crece).
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from ...config import get_settings
from .index import Chunk, _load

IMAGE_KIND = "pagina-imagen"


def dense_dir() -> Path:
    from ...models import embed_gemma as eg

    return get_settings().index_dir / f"dense_{eg.MODEL_ID.split('/')[-1]}_{eg.DIM}"


def _opinion_pages(log=print) -> list[tuple[Chunk, Path]]:
    """Páginas de los PDF de la Opinión Corporativa → (fragmento con el texto de la página, PNG de la página)."""
    from ...corpus import pdf_page_images, pdf_pages

    s = get_settings()
    root = s.opinion_path
    if not root.exists():
        log(f"sin carpeta de Opinión Corporativa ({root}): no se indexan imágenes")
        return []
    img_dir = s.index_dir / "page_images"
    out = []
    for pdf in sorted(root.glob("*.pdf")):
        rel = pdf.relative_to(s.data_dir).as_posix()
        texts = {p.page: p.text for p in pdf_pages(pdf, rel)}
        for png in pdf_page_images(pdf, img_dir, scale=1.0):          # 72 ppp: de sobra para un embedding
            n = int(png.stem.rsplit("_p", 1)[1])
            out.append((Chunk(id=f"{rel}#img{n}", text=texts.get(n, "").strip() or f"(página {n} sin texto extraíble)",
                              source=rel, folder=rel.split("/")[0], section="Opinión Corporativa",
                              heading=f"p. {n} (imagen)", kind=IMAGE_KIND), png))
    log(f"imágenes: {len(out)} páginas de {len(list(root.glob('*.pdf')))} PDF")
    return out


def build_dense(with_images: bool = True, log=print) -> int:
    """Vectoriza los fragmentos del índice BM25 (y las páginas como imagen) y los guarda en disco."""
    from ...models import embed_gemma as eg

    chunks, _ = _load()
    t0 = time.perf_counter()
    log(f"vectorizando {len(chunks)} fragmentos con {eg.MODEL_ID} ({eg.DIM} d)… (la primera vez descarga el modelo)")
    vecs = [eg.embed_passages([c.text for c in chunks], [f"{c.source} · {c.heading}" for c in chunks],
                              show_progress=True)]
    metas = [c.to_dict() for c in chunks]
    if with_images:
        pages = _opinion_pages(log)
        if pages:
            vecs.append(eg.embed_images([p for _, p in pages], show_progress=True))
            metas += [c.to_dict() for c, _ in pages]
    out = dense_dir()
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", np.vstack(vecs).astype(np.float32))
    with (out / "meta.jsonl").open("w", encoding="utf-8") as fh:
        for m in metas:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    _load_dense.cache_clear()
    log(f"índice denso: {len(metas)} vectores → {out} · {time.perf_counter() - t0:.0f} s")
    return len(metas)


def available() -> bool:
    return (dense_dir() / "vectors.npy").exists()


@lru_cache(maxsize=1)
def _load_dense() -> tuple[np.ndarray, list[Chunk]]:
    d = dense_dir()
    if not (d / "vectors.npy").exists():
        raise FileNotFoundError(f"No hay índice denso en {d}. Ejecuta: uv run python scripts/rag_dense_index.py")
    vecs = np.load(d / "vectors.npy")
    chunks = [Chunk(**json.loads(line)) for line in (d / "meta.jsonl").open(encoding="utf-8")]
    return vecs, chunks


def search_dense(query: str, k: int | None = None) -> list[tuple[float, Chunk]]:
    from ...models.embed_gemma import embed_query

    k = k or get_settings().top_k
    vecs, chunks = _load_dense()
    sims = vecs @ embed_query(query)
    top = np.argsort(-sims)[:k]
    return [(round(float(sims[i]), 3), chunks[i]) for i in top]
