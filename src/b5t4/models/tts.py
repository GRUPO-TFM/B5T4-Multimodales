"""
Texto a voz con Kokoro (ONNX, Apache-2.0, local y gratis; corre en CPU).

Los modelos (~350 MB) se descargan una vez con `uv run python scripts/download_models.py` a `models/`.
Kokoro lee mal las cifras («61,5 mil M$»), así que antes de sintetizar se «verbalizan» con num2words:
el vídeo enseña la cifra exacta en pantalla y la voz la dice en palabras.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

from ..config import get_settings

SAMPLE_RATE = 24000


def verbalize(s: str) -> str:
    """Cifras y símbolos → palabras: «4,5 %» → «cuatro coma cinco por ciento»."""
    from num2words import num2words

    s = s.replace("mil M$", "mil millones de dólares").replace("mil M€", "mil millones de euros")
    s = s.replace("M$", "millones de dólares").replace("M€", "millones de euros")
    s = s.replace("×", " veces").replace("%", " por ciento").replace("$", " dólares").replace("€", " euros")
    s = s.replace("≈", "aproximadamente ")
    s = re.sub(r"(\d)\s*pp\b", r"\1 puntos porcentuales", s)
    s = re.sub(r"(\d)\s*pb\b", r"\1 puntos básicos", s)

    def num(m):
        t = m.group(0)
        if "." in t and "," not in t and len(t.split(".")[-1]) != 3:   # 61.5 escrito a la inglesa → decimal
            t = t.replace(".", ",")
        t = t.replace(".", "").replace(",", ".")
        try:
            v = float(t)
            return num2words(int(v) if v.is_integer() else round(v, 2), lang="es").replace(" punto ", " coma ")
        except Exception:
            return m.group(0)

    return re.sub(r"[+-]?\d[\d.]*(?:,\d+)?", num, s)


@lru_cache(maxsize=1)
def _engine():
    from kokoro_onnx import Kokoro

    m = get_settings().models_dir
    onnx, voices = m / "kokoro-v1.0.onnx", m / "voices-v1.0.bin"
    if not onnx.exists():
        raise FileNotFoundError(f"Faltan los modelos de voz en {m}. Ejecuta: uv run python scripts/download_models.py")
    return Kokoro(str(onnx), str(voices))


def synthesize(text: str, voice: str | None = None, speed: float | None = None) -> tuple[np.ndarray, int]:
    """Devuelve (muestras float32, frecuencia). La duración del audio fija la duración de la escena del vídeo."""
    s = get_settings()
    samples, sr = _engine().create(text, voice=voice or s.voice, speed=speed or s.speed, lang="es")
    return samples.astype(np.float32), sr


def save_wav(text: str, path, **kw) -> float:
    """Sintetiza y guarda; devuelve la duración en segundos (útil para el agente RAG: respuesta en voz)."""
    import soundfile as sf

    samples, sr = synthesize(verbalize(text), **kw)
    sf.write(str(path), samples, sr)
    return len(samples) / sr
