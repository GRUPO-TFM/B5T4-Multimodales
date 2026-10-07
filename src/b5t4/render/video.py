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
import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..models import tts
from .schemas import Storyboard

PAD_AFTER, LEAD_IN = 0.5, 0.3   # silencio tras la locución y antes de que empiece a hablar (s)


def narrate(sb: Storyboard, out: Path, log=print) -> dict:
    """Sintetiza la locución escena a escena y devuelve la línea temporal {total, scenes:[{id,start,duration}]}."""
    import soundfile as sf

    out.mkdir(parents=True, exist_ok=True)
    audio_dir = out / "audio"
    audio_dir.mkdir(exist_ok=True)
    s = get_settings()
    timeline, track, sr, t = [], [], tts.SAMPLE_RATE, 0.0
    for index, sc in enumerate(sb.scenes, 1):
        spoken = tts.verbalize(sc.narration)
        digest = hashlib.sha256(json.dumps([spoken, sb.voice, s.speed], ensure_ascii=False).encode()).hexdigest()[:16]
        audio = audio_dir / f"{index:02d}-{digest}.wav"
        if audio.exists():
            samples, sr = sf.read(audio, dtype="float32")
        else:
            samples, sr = tts.synthesize(spoken, voice=sb.voice)
            sf.write(audio, samples, sr, subtype="FLOAT")
        if sr != tts.SAMPLE_RATE or samples.ndim != 1 or not len(samples):
            raise ValueError("La voz debe ser mono, no vacía y a la frecuencia de Kokoro")
        voice_len = len(samples) / sr
        dur = max(sc.min_seconds, LEAD_IN + voice_len + PAD_AFTER)
        clip = np.concatenate([np.zeros(round(LEAD_IN * sr), np.float32), samples,
                               np.zeros(round((dur - LEAD_IN - voice_len) * sr), np.float32)])
        track.append(clip)
        dur = len(clip) / sr
        timeline.append({"id": sc.id, "kind": sc.kind, "start": round(t, 6), "duration": round(dur, 6),
                         "voice_seconds": round(voice_len, 3), "audio": audio.relative_to(out).as_posix()})
        t += dur
        log(f"  voz {sc.id} {voice_len:4.1f}s → escena {dur:4.1f}s")
    sf.write(out / "voz.wav", np.concatenate(track), sr)
    tl = {"total": sum(len(clip) for clip in track) / sr, "scenes": timeline}
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
    out.mkdir(parents=True, exist_ok=True)
    if [scene["id"] for scene in tl["scenes"]] != [scene.id for scene in sb.scenes] or tl["total"] <= 0:
        raise ValueError("La cronología no coincide con el storyboard")
    html = scene_html(sb, tl, template)
    (out / "escenas.html").write_text(html, encoding="utf-8")
    frames = Path(tempfile.mkdtemp(prefix="frames-", dir=out)).resolve()
    n = math.ceil(tl["total"] * s.fps)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("B5T4_CHROMIUM") or None)   # B5T4_CHROMIUM: un Chromium ya instalado (sin «playwright install»)
        pg = b.new_page(viewport={"width": s.width, "height": s.height})
        pg.set_content(html, wait_until="load")
        pg.evaluate("document.fonts.ready")
        # El diseño usa coordenadas 1920×1080; el viewport puede escalarse manteniendo 16:9.
        if s.width * 9 != s.height * 16:
            raise ValueError("El vídeo requiere dimensiones 16:9")
        pg.evaluate("scale => {document.body.style.transformOrigin='0 0'; document.body.style.transform=`scale(${scale})`;}", s.width / 1920)
        for sc in tl["scenes"]:
            pg.evaluate("t => render(t)", sc["start"] + sc["duration"] * .75)
            overflow = pg.evaluate("""id => {
                const root = document.getElementById(id);
                return [...root.querySelectorAll('.ob-title,.ob-card,.v2-title,.v2-card,.v2-node')].some(node => {
                    const rect = node.getBoundingClientRect();
                    return rect.right > innerWidth - 20 || rect.bottom > innerHeight - 90 * innerHeight / 1080
                        || node.scrollWidth > node.clientWidth + 2 || node.scrollHeight > node.clientHeight + 2;
                });
            }""", sc["id"])
            if overflow:
                pg.screenshot(path=str(out / "error_diseno.png"))
                raise ValueError(f"La escena {sc['id']} desborda el área legible; acorta sus tarjetas")
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
    # Se borra solo el directorio temporal creado para esta ejecución, dentro de out.
    frames.relative_to(out.resolve())
    if not frames.name.startswith("frames-"):
        raise ValueError("Directorio temporal inesperado")
    shutil.rmtree(frames)
    log(f"  vídeo {mp4.name}: {tl['total']:.1f} s, {n} fotogramas")
    return mp4


def scene_html(sb: Storyboard, tl: dict, template="scene.html") -> str:
    """HTML autónomo: recursos v2 locales incrustados, contratos anteriores compatibles."""
    s = get_settings()
    v2 = all(scene.data.get("layout") == "onboarding_v2" for scene in sb.scenes)
    data = {**sb.model_dump(), "brand": s.brand}
    css = script = libraries = ""
    if v2:
        from .brand import logo_url, VENDOR_DIR
        data["logo_url"] = logo_url()
        css = (s.templates_dir / "onboarding-v2.css").read_text(encoding="utf-8")
        script = (s.templates_dir / "onboarding-v2.js").read_text(encoding="utf-8")
        libraries = "\n".join("<script>" + path.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
                              for path in (VENDOR_DIR / "gsap-3.15.0.min.js", VENDOR_DIR / "d3-7.9.0.min.js"))
    return ((s.templates_dir / template).read_text(encoding="utf-8")
            .replace("__SB__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__TL__", json.dumps(tl)).replace("__V2_CSS__", css)
            .replace("__V2_LIBS__", libraries).replace("__V2_JS__", script))


def inspect_video(path: Path) -> dict:
    """Decodifica el MP4 completo y comprueba que contiene imagen y audio válidos."""
    result = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("El MP4 no se decodifica correctamente: " + result.stderr[-600:])
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", result.stderr)
    dimensions = re.search(r"Video: h264[^\n]*? (\d{2,5})x(\d{2,5})", result.stderr)
    if not duration or not dimensions or "Audio: aac" not in result.stderr:
        raise ValueError("Se esperaba un MP4 H.264 con audio AAC y duración conocida")
    hours, minutes, seconds = map(float, duration.groups())
    return {"duration": hours * 3600 + minutes * 60 + seconds, "width": int(dimensions[1]),
            "height": int(dimensions[2]), "video_codec": "h264", "audio_codec": "aac",
            "bytes": path.stat().st_size, "decoded": True}


def make_video(sb: Storyboard, out: Path, log=print) -> Path:
    """Atajo para los agentes: storyboard → MP4 en `out`."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "storyboard.json").write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    est = sb.estimated_seconds(get_settings().words_per_second)
    log(f"  storyboard: {len(sb.scenes)} escenas, {sb.words()} palabras, ≈{est:.0f} s estimados")
    return render(sb, narrate(sb, out, log), out, log=log)
