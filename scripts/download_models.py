"""Descarga los modelos de voz Kokoro (≈350 MB, Apache-2.0) a models/. Solo hace falta una vez."""
import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
dst = Path(__file__).resolve().parent.parent / "models"; dst.mkdir(exist_ok=True)
for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
    p = dst / f
    if p.exists(): print("ya existe", f); continue
    print("descargando", f, "…"); urllib.request.urlretrieve(BASE + f, p); print("ok", f, p.stat().st_size // 1_000_000, "MB")
