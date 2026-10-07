"""
Voz a texto con faster-whisper (CTranslate2, MIT, local y gratis; corre en CPU).

Implementa la interfaz que esperan los agentes (ver models/stt.py): `transcribe(wav_path) -> str`.
Se deja en un fichero aparte para no tocar el esqueleto común mientras el equipo trabaja en paralelo.

Modelo: `small` por defecto (≈ 460 MB, una pregunta de 5-10 s en 1-3 s de CPU con int8). Se cambia con la
variable de entorno B5T4_STT_MODEL (`base`, `medium`, `large-v3-turbo`…). La primera llamada descarga el modelo
de Hugging Face a la caché local; después funciona sin conexión.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path

DEFAULT_MODEL = "small"
# Sesgo para el decodificador: vocabulario del equipo que Whisper no conoce (mejora nombres y siglas)
PROMPT = ("Pregunta de un empleado de Gestión Discrecional de Andbank: carteras, secciones Alpha, Beta, Temática, "
          "High Yield, Investment Grade, Opinión Corporativa, Luxemburgo, Unit Link, NextPortfolio, boleta.")


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel

    name = os.environ.get("B5T4_STT_MODEL", DEFAULT_MODEL)
    return WhisperModel(name, device="cpu", compute_type="int8")


def transcribe(wav_path: Path | str, language: str = "es") -> str:
    """Audio (wav, mp3, webm… lo que grabe el navegador) → texto en español."""
    segments, _ = _model().transcribe(str(wav_path), language=language, beam_size=1, vad_filter=True,
                                      initial_prompt=PROMPT)
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe_timed(wav_path: Path | str, language: str = "es") -> tuple[str, float]:
    t0 = time.perf_counter()
    text = transcribe(wav_path, language)
    return text, round(time.perf_counter() - t0, 2)
