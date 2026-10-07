"""
AGENTE 3 · Preguntas de empleados (RAG) — pasos 2 y 3: recuperar y responder.

Ejemplos del tipo de pregunta que debe resolver (golden set en evals/preguntas_rag.yaml):
  «¿A qué correo hay que enviar la operativa de Luxemburgo?»
  «¿Cuál es la mesa de ejecución de personas físicas y quiénes son sus responsables?»
  «¿Quién gestiona la sección Alpha y qué objetivos tiene?»

Flujo:
  1. retrieve(question)   [hecho]     BM25 sobre el índice → top_k fragmentos (index.search).
                          [pendiente] + embeddings y fusión RRF (búsqueda híbrida); filtros por sección.
  2. answer(question)     [hecho]     LLM: respuesta breve en español, con citas [n] a los fragmentos; si los
                                      fragmentos no lo dicen → «No consta en la documentación» (regla de honestidad).
                                      Sin clave de OpenRouter → modo extractivo: devuelve los pasajes, sin redactar.
  3. verify(answer)       [pendiente] Jev: cada frase contra el fragmento que cita; lo no respaldado se quita.
  4. speak(answer)        [hecho]     Kokoro: respuesta en voz (si están los modelos en models/).
                          [pendiente] pregunta por voz (models.stt).

Medición: `uv run b5t4 rag eval` → recall@k de la fuente esperada en el golden set (y respuestas, con --answers).
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from pydantic import BaseModel, Field

from ...config import get_settings
from .index import Chunk, search

NO_CONSTA = "No consta en la documentación."
PASSAGE_WORDS = 320   # recorte de cada fragmento en el prompt: suficiente contexto, prompt barato


class Citation(BaseModel):
    n: int
    source: str
    heading: str


class Answer(BaseModel):
    question: str
    text: str = Field(..., description="respuesta en español, 1-5 frases, con marcas [n]")
    citations: list[Citation] = Field(default_factory=list)
    found: bool = Field(True, description="False si la documentación no contiene la respuesta")
    mode: str = Field("llm", description="«llm» (respuesta redactada) o «extractivo» (sin clave: solo pasajes)")
    seconds: float | None = None
    timings: dict[str, float] = Field(default_factory=dict, description="segundos por paso: buscar, llm, voz")
    audio_path: str | None = None


class _LLMAnswer(BaseModel):
    """Lo que se le pide al LLM. Se valida con Pydantic antes de usarlo."""
    found: bool = Field(..., description="true solo si los pasajes contienen la respuesta")
    text: str = Field(..., description="respuesta en español, 1-5 frases, con marcas [n] tras cada dato")
    used: list[int] = Field(default_factory=list, description="números de los pasajes citados")


SYSTEM = f"""Eres el asistente interno del equipo de Gestión Discrecional de Andbank. Respondes preguntas de
empleados usando EXCLUSIVAMENTE los pasajes numerados que se te dan.

Reglas:
- Responde en español, en 1 a 5 frases, directo al dato que se pide (correo, persona, regla, fecha, cifra).
- Después de cada dato pon la marca del pasaje que lo respalda: [1], [2]…
- Copia literalmente correos, nombres, cifras y nombres de fichero; no los reformules.
- Si los pasajes NO contienen la respuesta, pon found=false y text="{NO_CONSTA}". No completes con conocimiento
  general ni supongas.
- Si un dato se deduce (por ejemplo, el nombre de una persona a partir de su correo), dilo explícitamente."""


def _passages(hits: list[tuple[float, Chunk]]) -> str:
    blocks = []
    for n, (_, c) in enumerate(hits, 1):
        words = c.text.split()
        body = " ".join(words[:PASSAGE_WORDS]) + (" […]" if len(words) > PASSAGE_WORDS else "")
        blocks.append(f"[{n}] Fuente: {c.source} · {c.heading}\n{body}")
    return "\n\n".join(blocks)


def _speak(text: str) -> str | None:
    s = get_settings()
    if not ((s.models_dir / "kokoro-v1.0.onnx").exists() and (s.models_dir / "voices-v1.0.bin").exists()):
        return None
    from ...models.tts import save_wav

    clean = re.sub(r"\s*\[\d+\]", "", text)                       # las marcas [n] no se leen en voz alta
    path = s.out_dir / "rag" / f"respuesta_{datetime.now():%Y%m%d_%H%M%S}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_wav(clean, path)
    return str(path)


def ask(question: str, voice: bool = False, k: int | None = None, log=print, *,
        hits: list[tuple[float, Chunk]] | None = None) -> Answer:
    """Responde con los fragmentos proporcionados, o busca si `hits` es None."""
    t0 = time.perf_counter()
    s = get_settings()
    if hits is None:
        hits = search(question, k or s.top_k)
    t_search = time.perf_counter()
    if not hits:
        ans = Answer(question=question, text=NO_CONSTA, found=False, mode="llm" if s.has_llm else "extractivo")
    elif not s.has_llm:
        # Modo extractivo: sin LLM no se redacta nada; se enseña el mejor pasaje y de dónde sale.
        _, top = hits[0]
        lines = [ln for ln in top.text.splitlines() if ln.strip()][:14]   # se respeta el formato (tablas, listas)
        ans = Answer(question=question, mode="extractivo",
                     text="*Sin LLM configurado: este es el pasaje más relevante [1].*\n\n" + "\n".join(lines) + "\n\n[…]",
                     citations=[Citation(n=n, source=c.source, heading=c.heading) for n, (_, c) in enumerate(hits[:3], 1)])
    else:
        from ...models.llm import ask_json

        user = f"Pregunta: {question}\n\nPasajes:\n\n{_passages(hits)}"
        out = ask_json(_LLMAnswer, SYSTEM, user, log=log)
        used = sorted({n for n in out.used if 1 <= n <= len(hits)} |
                      {int(n) for n in re.findall(r"\[(\d+)\]", out.text) if 1 <= int(n) <= len(hits)})
        ans = Answer(question=question, text=out.text if out.found else NO_CONSTA, found=out.found,
                     citations=[Citation(n=n, source=hits[n - 1][1].source, heading=hits[n - 1][1].heading)
                                for n in used] if out.found else [])
    t_llm = time.perf_counter()
    if voice and ans.mode == "llm":   # en modo extractivo no se lee el pasaje en voz alta (son tablas)
        ans.audio_path = _speak(ans.text)
    t_end = time.perf_counter()
    ans.timings = {"buscar": round(t_search - t0, 2), "llm": round(t_llm - t_search, 2), "voz": round(t_end - t_llm, 2)}
    ans.seconds = round(t_end - t0, 2)
    return ans
