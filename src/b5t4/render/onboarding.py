"""Informe de referencia e infografía v2 con identidad común y referencias legibles."""
from __future__ import annotations
import base64
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import get_settings
from .brand import logo_url, VENDOR_DIR


def image_url(path: Path):
    from PIL import Image
    with Image.open(path) as image:
        mime = Image.MIME.get(image.format, "image/png")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def source_index(bank, material):
    ids = sorted({sid for fact in bank.published().values() for sid in fact.source_ids})
    entries, mapping, keys = [], {}, {}
    for sid in ids:
        source = material.evidence[sid]
        key = (source.source, source.heading)
        if key not in keys:
            number = len(entries) + 1; keys[key] = number
            entries.append({"number": number, "path": source.source, "location": source.heading})
        mapping[sid] = keys[key]
    return entries, mapping


def referenced(ids, bank, mapping):
    published = bank.published()
    return sorted({mapping[sid] for cid in ids for sid in published[cid].source_ids})


def resources():
    templates = get_settings().templates_dir
    return {"logo": logo_url(), "v2_css": (templates / "onboarding-v2.css").read_text(encoding="utf-8"),
            "v2_js": (templates / "onboarding-v2.js").read_text(encoding="utf-8"),
            "libraries": "\n".join("<script>" + file.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
                        for file in (VENDOR_DIR / "gsap-3.15.0.min.js", VENDOR_DIR / "d3-7.9.0.min.js"))}


def write_reference(guide, bank, brief, material, out, direction=None, images=None):
    entries, mapping = source_index(bank, material)
    chapters = []
    by_id = {chapter.id: chapter for chapter in bank.chapters}
    for chapter in guide.chapters:
        data = chapter.model_dump()
        for paragraph in data["paragraphs"]:
            paragraph["refs"] = referenced(paragraph["claim_ids"], bank, mapping)
        for row in data["rows"]:
            row["refs"] = referenced(row["claim_ids"], bank, mapping)
        data["gaps"] = by_id[chapter.id].gaps
        candidates = [module for module in direction.modules if module.kind in ("organisation", "process")
                      and any(cid.startswith(chapter.id + "-") for item in module.items for cid in item.claim_ids)] if direction else []
        data["diagram"] = candidates[0].model_dump() if candidates else None
        chapters.append(data)
    cover = image_url(next(iter(images.values()))) if images else ""
    env = Environment(loader=FileSystemLoader(get_settings().templates_dir), autoescape=select_autoescape(["html"]))
    html = env.get_template("reference-v2.html").render(title=guide.title, brief=brief, chapters=chapters,
        sources=entries, cover=cover, **resources())
    (out / "informe.html").write_text(html, encoding="utf-8")
    lines = ["# " + guide.title, f"Dirigido a: {brief.role}. Área: {brief.area}.", "Documento de referencia · Andbank"]
    for chapter in chapters:
        lines.append("## " + chapter["title"])
        for paragraph in chapter["paragraphs"]:
            lines.append(paragraph["text"] + " " + " ".join(f"[{ref}]" for ref in paragraph["refs"]))
        if chapter["rows"]:
            lines += ["### " + (chapter["table_title"] or "Referencia práctica"), "| Concepto | Detalle |", "|---|---|"]
            lines += ["| " + row["label"].replace("|", "/") + " | " + row["detail"].replace("|", "/")
                      + " " + " ".join(f"[{ref}]" for ref in row["refs"]) + " |" for row in chapter["rows"]]
        if chapter["gaps"]:
            lines.append("### Información pendiente o con matices")
            lines.extend("- " + gap for gap in chapter["gaps"])
    lines.append("## Fuentes")
    lines.extend(f"[{source['number']}] {source['path']} · {source['location']}" for source in entries)
    (out / "informe.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_infographic(direction, bank, brief, material, out):
    from playwright.sync_api import sync_playwright
    entries, mapping = source_index(bank, material)
    blocks = []
    for module in direction.modules:
        data = module.model_dump()
        data["refs"] = referenced([cid for item in module.items for cid in item.claim_ids], bank, mapping)
        blocks.append(data)
    env = Environment(loader=FileSystemLoader(get_settings().templates_dir), autoescape=select_autoescape(["html"]))
    html = env.get_template("infographic-v2.html").render(brief=brief, title=bank.title, blocks=blocks, **resources())
    (out / "infografia.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.set_content(html, wait_until="load"); page.evaluate("document.fonts.ready")
            page.screenshot(path=str(out / "infografia.png"), full_page=True)
        finally:
            browser.close()


def render_graphics_script():
    return """document.querySelectorAll('.diagram[data-module]').forEach(host=>{
        onboardingV2.graph(host,JSON.parse(host.dataset.module));
    });"""
