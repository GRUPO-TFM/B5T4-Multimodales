"""
Voz del vídeo del agente 2: Gemini TTS (vía OpenRouter, la misma clave que el resto) con Kokoro de respaldo.

Por qué Gemini y no Kokoro: Kokoro es gratis y corre en local, pero su prosodia en español es plana y hay que
«traducirle» las cifras (verbalize). Gemini 3.8 Flash TTS lee «5,00 %» o «+75 pb» como un locutor, admite una
instrucción de estilo en lenguaje natural y cuesta ≈ 0,03 $ por vídeo de dos minutos (9 $ por millón de tokens de
audio, ≈ 32 tokens por segundo; el precio se duplica en enero de 2027 según Google). Puesto 2 en el test ciego de
Artificial Analysis (ElevenLabs v3, puesto 17).

Robustez: si no hay clave, OpenRouter falla o el audio no se puede decodificar, TODO el vídeo se sintetiza con
Kokoro (nunca se mezclan dos voces). Cada frase se guarda en index/opinion/voz/<hash>.wav: una frase ya
sintetizada no se vuelve a pagar (el guion cambia poco entre ejecuciones).

Configuración en config/b5t4.toml, sección [opinion.tts]: provider = "gemini" | "kokoro", model, voice, style.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

from ...config import CONFIG_FILE, get_settings
from ...models import tts as kokoro
from .llmcall import Usage

SAMPLE_RATE = 24000      # Gemini TTS y Kokoro emiten a 24 kHz: una sola pista sin remuestrear
PAD_AFTER, LEAD_IN = 0.5, 0.3


@dataclass
class TTSConfig:
    provider: str = "gemini"
    model: str = "google/gemini-3.8-flash-tts"
    voice: str = "Charon"                # voz de estudio de Gemini, timbre masculino e informativo
    style: str = ("Lee en español de España como un presentador de informes financieros: tono sereno, claro y "
                  "pausado, sin énfasis dramático. Pronuncia las cifras y los porcentajes de forma natural.")


def load_tts_config() -> TTSConfig:
    o = {}
    if CONFIG_FILE.exists():
        o = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("opinion", {}).get("tts", {})
    return TTSConfig(**{k: v for k, v in o.items() if k in TTSConfig.__dataclass_fields__})


def _cache_dir() -> Path:
    d = get_settings().index_dir / "opinion" / "voz"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _decode(raw: bytes) -> tuple[np.ndarray, int]:
    """WAV (cabecera RIFF) o PCM 16 bits crudo a 24 kHz → muestras float32 mono."""
    import soundfile as sf

    if raw[:4] == b"RIFF":
        data, sr = sf.read(io.BytesIO(raw), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data.astype(np.float32), int(sr)
    return (np.frombuffer(raw[: len(raw) - len(raw) % 2], dtype="<i2").astype(np.float32) / 32768.0), SAMPLE_RATE


def _gemini(text: str, cfg: TTSConfig, usage: Usage | None, log) -> tuple[np.ndarray, int]:
    """Una frase → audio, por el endpoint de chat de OpenRouter con salida de audio (va en streaming SSE:
    se concatenan los trozos base64 de delta.audio.data)."""
    s = get_settings()
    if not s.openrouter_api_key:
        raise RuntimeError("sin OPENROUTER_API_KEY")
    payload = {"model": cfg.model, "stream": True, "modalities": ["text", "audio"],
               "audio": {"voice": cfg.voice, "format": "pcm16"},
               "messages": [{"role": "system", "content": cfg.style}, {"role": "user", "content": text}]}
    r = requests.post(s.llm_url, timeout=120, json=payload, stream=True, headers={
        "Authorization": f"Bearer {s.openrouter_api_key}", "Content-Type": "application/json", "X-Title": "MIAX B5-T4 · opinion"})
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:200]}")
    chunks, u = [], {}
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            d = json.loads(body)
        except ValueError:
            continue
        u = d.get("usage") or u
        for ch in d.get("choices", []):
            a = (ch.get("delta") or {}).get("audio") or (ch.get("message") or {}).get("audio") or {}
            if a.get("data"):
                chunks.append(a["data"])
    if not chunks:
        raise RuntimeError("OpenRouter no ha devuelto audio")
    if usage is not None and u:
        usage.add(cfg.model, u)
    samples, sr = _decode(base64.b64decode("".join(chunks)))
    if len(samples) < sr * 0.3:
        raise RuntimeError("audio demasiado corto")
    return samples, sr


def synthesize(text: str, cfg: TTSConfig, usage: Usage | None = None, log=print) -> tuple[np.ndarray, int]:
    """Audio de una frase con el proveedor configurado, con caché por frase. Lanza excepción si Gemini falla:
    quien llama decide el respaldo (narrate: todo el vídeo con Kokoro)."""
    import soundfile as sf

    if cfg.provider != "gemini":
        return kokoro.synthesize(kokoro.verbalize(text), voice=get_settings().voice)
    key = hashlib.sha1(f"{cfg.model}|{cfg.voice}|{cfg.style}|{text}".encode()).hexdigest()[:20]
    wav = _cache_dir() / f"{key}.wav"
    if wav.exists():
        data, sr = sf.read(wav, dtype="float32")
        return data.astype(np.float32), int(sr)
    samples, sr = _gemini(text, cfg, usage, log)
    sf.write(wav, samples, sr)
    return samples, sr


def narrate(sb, out: Path, usage: Usage | None = None, log=print) -> dict:
    """Misma salida que render.video.narrate (voz.wav + timeline.json), con el proveedor de voz de este agente.
    Si Gemini falla en cualquier escena, se rehace TODO con Kokoro para no mezclar voces."""
    import soundfile as sf

    from concurrent.futures import ThreadPoolExecutor

    cfg = load_tts_config()
    for attempt in (cfg.provider, "kokoro"):
        cfg.provider = attempt
        try:
            timeline, track, t = [], [], 0.0
            # Gemini: las escenas se sintetizan en paralelo (llamadas de red independientes); Kokoro, en serie (CPU)
            with ThreadPoolExecutor(max_workers=4 if attempt == "gemini" else 1) as ex:
                audios = list(ex.map(lambda sc: synthesize(sc.narration, cfg, usage, log), sb.scenes))
            for sc, (samples, sr) in zip(sb.scenes, audios):
                voice_len = len(samples) / sr
                dur = max(sc.min_seconds, LEAD_IN + voice_len + PAD_AFTER)
                track.append(np.concatenate([np.zeros(int(LEAD_IN * sr), np.float32), samples,
                                             np.zeros(max(0, int((dur - LEAD_IN - voice_len) * sr)), np.float32)]))
                timeline.append({"id": sc.id, "kind": sc.kind, "start": round(t, 3), "duration": round(dur, 3),
                                 "voice_seconds": round(voice_len, 2)})
                t += dur
                log(f"  voz {attempt} {sc.id} {voice_len:4.1f}s → escena {dur:4.1f}s")
            break
        except Exception as e:
            if attempt == "kokoro":
                raise
            log(f"  voz: Gemini TTS no disponible ({str(e)[:120]}); todo el vídeo con Kokoro")
    sf.write(out / "voz.wav", np.concatenate(track), sr)
    tl = {"total": round(t, 3), "scenes": timeline, "voice": f"{attempt}:{cfg.voice if attempt == 'gemini' else get_settings().voice}"}
    (out / "timeline.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")
    return tl
