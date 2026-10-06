"""
Informe escrito: Markdown → HTML responsive con una plantilla Jinja2.

Los agentes producen el informe en Markdown (fácil de generar, de revisar y de versionar) y esta capa lo
viste: tipografía, colores de marca, tablas con scroll propio en el móvil. Así ningún agente se ocupa de CSS.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import get_settings


def md_to_html(md: str) -> str:
    """Conversor mínimo (títulos, listas, tablas, negritas, código). Suficiente para informes generados;
    si se quiere más, cambiar por `markdown-it-py` sin tocar a los agentes."""
    lines, out, i = md.splitlines(), [], 0
    inline = lambda t: re.sub(r"`([^`]+)`", r"<code>\1</code>", re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(t)))
    while i < len(lines):
        ln = lines[i]
        if m := re.match(r"^(#{1,4}) (.+)", ln):
            n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            head = [c.strip() for c in ln.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(h)}</th>" for h in head)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
                       + "</tbody></table></div>")
            continue
        if re.match(r"^\s*[-*] ", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append(inline(re.sub(r"^\s*[-*] ", "", lines[i]))); i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"); continue
        if ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


def write_report(markdown: str, title: str, out: Path, extra: dict | None = None) -> Path:
    """Guarda `informe.md` e `informe.html` en `out` y devuelve la ruta del HTML."""
    s = get_settings()
    out.mkdir(parents=True, exist_ok=True)
    (out / "informe.md").write_text(markdown, encoding="utf-8")
    env = Environment(loader=FileSystemLoader(s.templates_dir), autoescape=select_autoescape(["html"]))
    html = env.get_template("report.html").render(title=title, body=md_to_html(markdown), brand=s.brand,
                                                  date=dt.date.today().strftime("%d-%m-%Y"), **(extra or {}))
    p = out / "informe.html"
    p.write_text(html, encoding="utf-8")
    return p
