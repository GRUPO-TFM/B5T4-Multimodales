"""
AGENTE 3 · Preguntas de empleados (RAG) — pasos 2 y 3: recuperar y responder.

Ejemplos del tipo de pregunta que debe resolver (golden set en evals/preguntas_rag.yaml):
  «¿A qué correo hay que enviar la operativa de Luxemburgo?»
  «¿Cuál es la mesa de ejecución de personas físicas y quiénes son sus responsables?»
  «¿Quién gestiona la sección Alpha y qué objetivos tiene?»

Flujo previsto:
  1. route(question)      [barato]  filtros de metadatos: ¿menciona una sección, una persona, un tipo de documento?
                                    (diccionario de alias a partir de los contextos: «HY» → 14., «Luxemburgo» → 20.)
  2. retrieve(question)   híbrido BM25 + embeddings, fusión por rangos (RRF), top_k fragmentos, priorizando
                          los de contexto (ya están escritos para responder).
  3. answer(question)     [LLM] respuesta breve en español con citas [n] a la fuente; si los fragmentos no lo
                          dicen, responde «no consta en la documentación» (regla de honestidad).
  4. verify(answer)       [Jev] cada frase de la respuesta contra el fragmento citado; lo no respaldado se quita.
  5. speak(answer)        [Kokoro] respuesta en voz (models.tts.save_wav); la pregunta puede llegar por voz
                          (models.stt.transcribe).

Medición: acierto en el golden set, recall@k de la fuente esperada y latencia (objetivo < 3 s sin voz).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    n: int
    source: str
    heading: str


class Answer(BaseModel):
    question: str
    text: str = Field(..., description="respuesta en español, 1-5 frases, con marcas [n]")
    citations: list[Citation] = Field(default_factory=list)
    found: bool = Field(True, description="False si la documentación no contiene la respuesta")
    audio_path: str | None = None


def ask(question: str, voice: bool = False) -> Answer:
    raise NotImplementedError("RAG pendiente: route → retrieve → answer → verify → speak (ver docstring).")
