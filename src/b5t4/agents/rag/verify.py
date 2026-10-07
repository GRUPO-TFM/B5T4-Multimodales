"""
AGENTE 3 · paso 3: verificar la respuesta frase a frase con Jev.

Cada frase de la respuesta lleva marcas [n] a los fragmentos que la respaldan. Aquí se comprueba, frase a frase,
que el fragmento citado de verdad lo dice (models.verifier.supports → probabilidad calibrada) y se decide con
los umbrales de la configuración (verifier.triage):
  publicar  (p ≥ 0,80)  la frase se queda tal cual;
  revisar   (0,30-0,80) se queda, marcada con ⚠️;
  descartar (p < 0,30)  se quita de la respuesta.
Una frase sin cita no puede verificarse: se marca para revisar.

Sin JEV_API_KEY no se verifica nada: la respuesta pasa igual y `verified=False` lo deja claro en la interfaz.
Se usa desde `ask_verified()`, que envuelve el `ask()` existente sin modificarlo.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

from pydantic import BaseModel, Field

from ...models import verifier
from .answer import NO_CONSTA, Answer, ask
from .index import Chunk, search

PASSAGE_CHARS = 6000          # el pasaje que ve Jev: el fragmento completo, con tope
WARN = "⚠️"
_CITE = re.compile(r"\[(\d+)\]")
_ASK_LOCK = threading.Lock()   # ask() se reutiliza cambiando su buscador un instante: una petición cada vez


class SentenceCheck(BaseModel):
    text: str
    cites: list[int] = Field(default_factory=list)
    p: Optional[float] = None           # probabilidad de que la(s) fuente(s) citadas lo respalden
    decision: str = "sin verificar"     # publicar · revisar · descartar · sin verificar


class VerifiedAnswer(BaseModel):
    answer: Answer                      # la respuesta tal como la dio el LLM
    text: str                           # la respuesta después de verificar
    sentences: list[SentenceCheck] = Field(default_factory=list)
    verified: bool = False
    seconds: float = 0.0

    @property
    def removed(self) -> int:
        return sum(s.decision == "descartar" for s in self.sentences)

    @property
    def flagged(self) -> int:
        return sum(s.decision == "revisar" for s in self.sentences)


def split_sentences(text: str) -> list[str]:
    """Frases, dejando las marcas [n] pegadas a la frase a la que siguen («… .lu [1], [2]. Asimismo …»)."""
    text = re.sub(r"\s+", " ", text).strip()
    # corta tras . ! ? (con citas opcionales detrás) cuando sigue una mayúscula o un signo de apertura
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«(])", text)
    return [p.strip() for p in parts if p.strip()]


def cited(sentence: str, n_passages: int) -> list[int]:
    return sorted({int(n) for n in _CITE.findall(sentence) if 1 <= int(n) <= n_passages})


def check_sentences(text: str, passages: list[Chunk],
                    supports: Callable[[str, str], float | None] = verifier.supports,
                    triage: Callable[[float | None], str] = verifier.triage) -> list[SentenceCheck]:
    """Verifica cada frase contra la unión de los fragmentos que cita. `supports`/`triage` se inyectan en las pruebas."""
    out = []
    for sen in split_sentences(text):
        ns = cited(sen, len(passages))
        claim = _CITE.sub("", sen).strip()
        if not ns:
            out.append(SentenceCheck(text=sen, decision="revisar"))
            continue
        passage = "\n\n".join(f"[{n}] {passages[n - 1].text}" for n in ns)[:PASSAGE_CHARS]
        p = supports(claim, passage)
        out.append(SentenceCheck(text=sen, cites=ns, p=p, decision=triage(p)))
    return out


def rebuild(checks: list[SentenceCheck]) -> str:
    kept = []
    for c in checks:
        if c.decision == "descartar":
            continue
        kept.append(f"{c.text} {WARN}" if c.decision == "revisar" else c.text)
    return " ".join(kept) if kept else NO_CONSTA


def ask_verified(question: str, voice: bool = False, k: int | None = None, search_fn=search,
                 verify: bool = True, log=print) -> VerifiedAnswer:
    """
    `ask()` + verificación. `search_fn` permite usar otro buscador (p. ej. hybrid.search_hybrid) sin tocar ask():
    se le pasan a ask los mismos fragmentos que se verificarán, para que los números [n] coincidan.
    """
    from . import answer as answer_mod

    t0 = time.perf_counter()
    hits = search_fn(question, k) if k else search_fn(question)
    t_search = round(time.perf_counter() - t0, 2)
    with _ASK_LOCK:
        original_search = answer_mod.search
        answer_mod.search = lambda *_a, **_k: hits      # ask() usa exactamente estos fragmentos
        try:
            ans = ask(question, voice=False, k=k, log=log)
        finally:
            answer_mod.search = original_search
    ans.timings["buscar"] = t_search

    passages = [c for _, c in hits]
    if not (verify and ans.found and ans.mode == "llm" and verifier.available()):
        res = VerifiedAnswer(answer=ans, text=ans.text, verified=False)
    else:
        t0 = time.perf_counter()
        checks = check_sentences(ans.text, passages)
        res = VerifiedAnswer(answer=ans, text=rebuild(checks), sentences=checks, verified=True,
                             seconds=round(time.perf_counter() - t0, 2))
        ans.timings["jev"] = res.seconds
        log(f"  jev: {len(checks)} frases · {res.removed} quitadas · {res.flagged} a revisar · {res.seconds} s")

    if voice and ans.mode == "llm":
        t0 = time.perf_counter()
        ans.audio_path = answer_mod._speak(res.text.replace(WARN, ""))
        ans.timings["voz"] = round(time.perf_counter() - t0, 2)
    return res
