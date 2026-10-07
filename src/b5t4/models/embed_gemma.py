"""
Embeddings multimodales con EmbeddingGemma 2 (Google DeepMind, Apache 2.0, publicado el 6-oct-2026).

Por qué este modelo (y no el `multilingual-e5-small` que proponía models/embeddings.py):
  - texto e IMAGEN en el mismo espacio vectorial → una pregunta escrita o hablada puede encontrar una página de
    PDF por lo que se VE en ella (gráficos y tablas de la Opinión Corporativa), no solo por su texto;
  - multilingüe (100+ idiomas), 8K de contexto, Matryoshka: se recorta a 256 dimensiones casi sin perder calidad.
Coste: necesita torch + sentence-transformers y descargar ~1,5 GB una vez. Se carga sin el codificador de audio.

Interfaz (la misma que models/embeddings.py, más imágenes):
    embed_passages(textos, titulos=None) -> np.ndarray (n, d) normalizado
    embed_query(texto)                   -> np.ndarray (d,)   normalizado
    embed_images(rutas)                  -> np.ndarray (n, d) normalizado

Variables de entorno opcionales: B5T4_EMB_MODEL (por defecto google/embeddinggemma-2), B5T4_EMB_DIM (256).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_ID = os.environ.get("B5T4_EMB_MODEL", "google/embeddinggemma-2")
DIM = int(os.environ.get("B5T4_EMB_DIM", "256"))      # 768 · 512 · 256 · 128 (Matryoshka)
BATCH = 8


@lru_cache(maxsize=1)
def _model():
    import torch
    from sentence_transformers import SentenceTransformer

    # float32 en CPU (el modelo NO admite float16); sin audio: 440M parámetros en lugar de 740M
    return SentenceTransformer(MODEL_ID, device="cpu", model_kwargs={"torch_dtype": torch.float32},
                               config_kwargs={"audio_config": None})


def _norm(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / np.clip(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12, None)


def _encode(inputs, show_progress: bool = False) -> np.ndarray:
    # truncate_dim + renormalizar: al recortar un vector unitario deja de serlo (lo exige la ficha del modelo)
    out = _model().encode(inputs, batch_size=BATCH, truncate_dim=DIM, normalize_embeddings=True,
                          convert_to_numpy=True, show_progress_bar=show_progress)
    return _norm(out)


def embed_passages(texts: list[str], titles: list[str] | None = None, show_progress: bool = False) -> np.ndarray:
    """Formato de documento que pide el modelo: «title: {título} | text: {contenido}» («none» si no hay título)."""
    titles = titles or ["none"] * len(texts)
    return _encode([f"title: {t or 'none'} | text: {x}" for t, x in zip(titles, texts)], show_progress)


def embed_query(text: str) -> np.ndarray:
    return _encode([f"task: question answering | query: {text}"])[0]


def embed_images(paths: list[Path], show_progress: bool = False) -> np.ndarray:
    """Imágenes sin prefijo (los prefijos son solo para texto). Una entrada multimodal por imagen."""
    from PIL import Image

    try:
        return _encode([{"image": str(p)} for p in paths], show_progress)
    except (TypeError, ValueError):   # versiones que no aceptan dict: se pasa la imagen ya abierta
        return _encode([Image.open(p).convert("RGB") for p in paths], show_progress)
