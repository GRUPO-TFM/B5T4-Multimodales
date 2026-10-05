"""
Motor de vídeo: storyboard → voz → fotogramas → MP4. Es el que ya funciona en el prototipo (2-oct-2026),
generalizado para los agentes 1 y 2.

Tres pasos deterministas:
  1. narrate(sb)       una pista de voz por escena con Kokoro; la duración del AUDIO fija la de la escena
                       (no al revés: así la voz nunca se corta ni sobra silencio).
  2. render_frames()   Chromium (Playwright) abre templates/scene.html, que expone una función JS render(t);
                       para cada instante t = i / fps se llama a render(t) y se hace una captura → JPG.
  3. ffmpeg            une los JPG y el WAV en un MP4 H.264 (ffmpeg del sistema o el de imageio-ffmpeg).

Coste: cero APIs. 60 s de vídeo a 25 fps son 1.500 capturas: ≈ 1-2 min de CPU.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..models import tts
from .schemas import Storyboard

PAD_AFTER, LEAD_IN = 0.5, 0.3   # silencio tras la locución y antes de que empiece a hablar (s)


def narrate(sb: Storyboard, out: Path, log=print) -> dict:
    """Sintetiza la locución escena a escena y devuelve la línea temporal {total, scenes:[{id,start,duration}]}."""
    import soundfile as sf

    timeline, track, sr, t = [], [], tts.SAMPLE_RATE, 0.0
    for sc in sb.scenes:
        samples, sr = tts.synthesize(tts.verbalize(sc.narration), voice=sb.voice)
        voice_len = len(samples) / sr
        dur = max(sc.min_seconds, LEAD_IN + voice_len + PAD_AFTER)
        track.append(np.concatenate([np.zeros(int(LEAD_IN * sr), np.float32), samples,
                                     np.zeros(int((dur - LEAD_IN - voice_len) * sr), np.float32)]))
        timeline.append({"id": sc.id, "kind": sc.kind, "start": round(t, 3), "duration": round(dur, 3),
                         "voice_seconds": round(voice_len, 2)})
        t += dur
        log(f"  voz {sc.id} {voice_len:4.1f}s → escena {dur:4.1f}s")
    sf.write(out / "voz.wav", np.concatenate(track), sr)
    tl = {"total": round(t, 3), "scenes": timeline}
    (out / "timeline.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")
    return tl


def _ffmpeg() -> str:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def render(sb: Storyboard, tl: dict, out: Path, template: str = "scene.html", log=print) -> Path:
    """Dibuja el storyboard fotograma a fotograma y lo mezcla con la voz. Devuelve la ruta del MP4."""
    from playwright.sync_api import sync_playwright

    s = get_settings()
    brand = s.brand   # texto de la pastilla de marca (admite HTML, p. ej. «Gestión <b>Discrecional</b>»)
    html = ((s.templates_dir / template).read_text(encoding="utf-8")
            .replace("__SB__", json.dumps({**sb.model_dump(), "brand": brand}, ensure_ascii=False))
            .replace("__TL__", json.dumps(tl)))
    (out / "escenas.html").write_text(html, encoding="utf-8")
    frames = out / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    n = int(round(tl["total"] * s.fps))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": s.width, "height": s.height})
        pg.set_content(html, wait_until="load")
        pg.wait_for_timeout(300)
        for i in range(n):
            pg.evaluate(f"render({i / s.fps})")
            pg.screenshot(path=str(frames / f"f_{i:05d}.jpg"), type="jpeg", quality=92)
            if i % 250 == 0:
                log(f"  fotograma {i}/{n}")
        for sc in tl["scenes"]:   # una captura fija por escena: sirve de infografía y de miniatura
            pg.evaluate(f"render({sc['start'] + sc['duration'] * 0.75})")
            pg.screenshot(path=str(out / f"escena_{sc['id']}.png"))
        b.close()
    mp4 = out / "video.mp4"
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-framerate", str(s.fps), "-i", str(frames / "f_%05d.jpg"),
                    "-i", str(out / "voz.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                    str(mp4)], check=True)
    shutil.rmtree(frames)
    log(f"  vídeo {mp4.name}: {tl['total']:.1f} s, {n} fotogramas")
    return mp4


def make_video(sb: Storyboard, out: Path, log=print) -> Path:
    """Atajo para los agentes: storyboard → MP4 en `out`."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "storyboard.json").write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    est = sb.estimated_seconds(get_settings().words_per_second)
    log(f"  storyboard: {len(sb.scenes)} escenas, {sb.words()} palabras, ≈{est:.0f} s estimados")
    return render(sb, narrate(sb, out, log), out, log=log)
