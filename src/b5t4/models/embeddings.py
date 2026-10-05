"""
Embeddings (pendiente — agente 3).

Un embedding convierte un texto en un vector: textos que significan lo mismo quedan cerca aunque usen
palabras distintas («operativa de Luxemburgo» ≈ «órdenes del Unit Link»). Es la mitad «semántica» del
retrieval; la otra mitad es BM25 (coincidencia de palabras exactas), imprescindible aquí porque las
preguntas de los empleados están llenas de nombres propios, correos y siglas (CCV, NDEEWNR, P4).

Propuesta: `intfloat/multilingual-e5-small` (multilingüe, 118 M parámetros, corre en CPU) vía fastembed o
sentence-transformers; ojo al prefijo «query: » / «passage: » que exige la familia e5.

Interfaz que espera el agente RAG (no cambiarla al implementar):
    embed_passages(textos) -> np.ndarray (n, d), normalizado
    embed_query(texto)     -> np.ndarray (d,), normalizado
"""
from __future__ import annotations

import numpy as np


def embed_passages(texts: list[str]) -> np.ndarray:
    raise NotImplementedError("Embeddings pendientes: ver docstring del módulo.")


def embed_query(text: str) -> np.ndarray:
    raise NotImplementedError("Embeddings pendientes: ver docstring del módulo.")
