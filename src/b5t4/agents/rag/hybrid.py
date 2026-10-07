"""
AGENTE 3 · búsqueda híbrida: BM25 (palabras exactas) + EmbeddingGemma 2 (significado, texto e imagen).

Se fusionan las dos listas por RANGO, no por puntuación (Reciprocal Rank Fusion):

    rrf(d) = Σ_listas  1 / (K + posición de d en la lista)

Las puntuaciones de BM25 (0-30) y del coseno (0-1) no son comparables; los rangos sí. K = 60 es el valor del
artículo original (Cormack et al., 2009): suaviza para que un único primer puesto no lo decida todo.
Un fragmento que sale arriba en las dos listas gana; uno que solo sale en una puede entrar si sale muy arriba.

Si no hay índice denso, cae a BM25 solo y lo dice: la demo nunca se rompe por falta de embeddings.
"""
from __future__ import annotations

from ...config import get_settings
from .index import Chunk, search

RRF_K = 60
CANDIDATES = 50     # cuántos candidatos aporta cada buscador antes de fusionar


def rrf(rankings: list[list[tuple[float, Chunk]]], k: int, rrf_k: int = RRF_K) -> list[tuple[float, Chunk]]:
    score: dict[str, float] = {}
    by_id: dict[str, Chunk] = {}
    for ranking in rankings:
        for pos, (_, c) in enumerate(ranking, 1):
            score[c.id] = score.get(c.id, 0.0) + 1.0 / (rrf_k + pos)
            by_id.setdefault(c.id, c)
    best = sorted(score.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return [(round(v, 5), by_id[i]) for i, v in best]


def search_hybrid(query: str, k: int | None = None, log=lambda *_: None) -> list[tuple[float, Chunk]]:
    from . import dense

    k = k or get_settings().top_k
    lexical = search(query, CANDIDATES)
    if not dense.available():
        log("sin índice denso: búsqueda solo BM25 (uv run python scripts/rag_dense_index.py)")
        return lexical[:k]
    return rrf([lexical, dense.search_dense(query, CANDIDATES)], k)
