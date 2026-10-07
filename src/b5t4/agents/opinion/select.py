"""
Paso 1 · ¿Qué documentos son Opinión Corporativa y cuáles son los dos últimos?

Tres comprobaciones independientes, sin LLM (gratis, instantáneo y siempre igual):
  1. el manifiesto los clasifica como «Opinión Corporativa (PDF del grupo)» y vigentes;
  2. la portada del PDF dice «Opinión corporativa» (o «Perspectivas estratégicas»): confirma el contenido;
  3. la fecha de edición va al principio del nombre (AAAA-MM-DD_…).
Si un PDF de la carpeta no tiene fecha en el nombre o su portada no encaja, se avisa en lugar de adivinar.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

from ...config import get_settings
from ...corpus import load_manifest
from .schemas import Edition

KIND = "Opinión Corporativa (PDF del grupo)"
_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})_Opinion_Corporativa_(.+)\.pdf$", re.I)


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def _cover_ok(path) -> bool:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        cover = _norm(" ".join(pdf[0].get_textpage().get_text_range().split()))
    finally:
        pdf.close()
    return "opinion corporativa" in cover or "perspectivas estrategicas" in cover


def _label(raw: str) -> str:
    lab = raw.replace("_", " ").replace("Mensual ", "").strip()
    return re.sub(r"^(\d)T (\d{4})$", r"\1T \2", lab)


def list_editions(log=print) -> list[Edition]:
    """Todas las ediciones válidas, de la más antigua a la más reciente."""
    s = get_settings()
    try:
        files = [f for f in load_manifest() if f.kind == KIND and f.is_current and f.path.exists()]
        paths = [(f.path, f.md5) for f in files]
    except FileNotFoundError:                      # sin manifiesto: se mira la carpeta configurada
        paths = [(p, "") for p in sorted(s.opinion_path.glob("*.pdf"))]
    eds = []
    for path, md5 in paths:
        m = _NAME.match(path.name)
        if not m:
            log(f"  aviso: {path.name} no lleva la fecha de edición en el nombre; se ignora")
            continue
        if not _cover_ok(path):
            log(f"  aviso: la portada de {path.name} no parece una Opinión Corporativa; se ignora")
            continue
        eds.append(Edition(date=dt.date.fromisoformat(m.group(1)), label=_label(m.group(2)), path=path, md5=md5))
    return sorted(eds, key=lambda e: e.date)


def latest_two(log=print) -> tuple[Edition, Edition]:
    eds = list_editions(log)
    if len(eds) < 2:
        raise RuntimeError(f"Hacen falta al menos dos ediciones de la Opinión Corporativa; hay {len(eds)}.")
    return eds[-2], eds[-1]
