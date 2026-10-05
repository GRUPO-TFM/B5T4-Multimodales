"""Agente 3 · Preguntas de empleados (RAG). Puntos de entrada: index.build_index / index.search / answer.ask."""
from .answer import Answer, ask
from .index import Chunk, build_chunks, build_index, search, tokenize

__all__ = ["Answer", "ask", "Chunk", "build_chunks", "build_index", "search", "tokenize"]
