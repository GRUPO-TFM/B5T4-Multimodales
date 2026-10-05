"""
Voz a texto (pendiente — agente 3): que un empleado pueda PREGUNTAR hablando.

Propuesta: faster-whisper (CTranslate2, MIT, local) con el modelo `small` o `medium` en español; en CPU
transcribe una pregunta de 5-10 s en 1-2 s. Alternativa sin instalar nada: la grabación del micrófono de
Gradio + la API de transcripción de OpenRouter, si el modelo elegido la admite.

Interfaz que esperan los agentes (no cambiarla al implementar):
    transcribe(wav_path) -> str
"""
from __future__ import annotations

from pathlib import Path


def transcribe(wav_path: Path) -> str:
    raise NotImplementedError("STT pendiente: implementar con faster-whisper (ver docstring del módulo).")
