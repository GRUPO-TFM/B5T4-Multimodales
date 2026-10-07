"""Infografía de datos verificados: organigrama, secciones, proceso y calendario.

HTML/CSS y Playwright producen HTML y PNG sin CDN ni servicios de imágenes.
Se conserva la interfaz write_infographic(blocks, title, out) -> Path.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import get_settings


def write_infographic(blocks: list[dict], title: str, out: Path) -> Path:
    """Dibuja los datos ya verificados con HTML/CSS local, sin dependencias de red."""
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    s = get_settings()
    env = Environment(loader=FileSystemLoader(s.templates_dir), autoescape=select_autoescape(["html"]))
    html = env.get_template("infographic.html").render(title=title, brand=s.brand, blocks=blocks)
    (out / "infografia.html").write_text(html, encoding="utf-8")
    target = out / "infografia.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(target), full_page=True)
        finally:
            browser.close()
    return target
