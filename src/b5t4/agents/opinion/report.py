"""
Paso 5 · Informe para clientes en HTML (móvil), gráficos PNG y cambios.json.

Nada de este paso usa LLM: maqueta lo ya calculado (comparación) y verificado (explicaciones). Cada dato del informe
lleva su fuente: la línea literal del PDF, la página y un enlace que abre el PDF en esa página; la tabla sinóptica
incluye la imagen de la página original. Los PNG se guardan sueltos: son la materia prima de la futura versión en vídeo.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...config import get_settings
from .catalog import ASSETS, REGION_ORDER, fmt_delta, group_es
from .compare import unchanged_views
from .llmcall import load_config
from .schemas import Change, EditionData

ROJO, GRIS, TINTA = "#D52B1E", "#928B81", "#1d1d1b"
STANCE_COLORS = {"NEGATIVO": "#a8322a", "INFRAPONDERAR": "#c9564c", "NEUTRAL-INFRAPONDERAR": "#e9b3ad",
                 "NEUTRAL": "#dcd7d1", "NEUTRAL-SOBREPONDERAR": "#a9cdb0", "SOBREPONDERAR": "#4f9a63",
                 "FAVORABLE": "#4f9a63", "OTRA": "#ffffff"}
LEGAL = ("Este documento resume, con fines exclusivamente informativos, los cambios entre dos ediciones de la "
         "Opinión Corporativa de Andbank. No constituye una recomendación personalizada, ni una oferta o solicitud de "
         "compra o venta de ningún instrumento financiero, y no tiene en cuenta los objetivos, la situación financiera "
         "ni el perfil de riesgo de ningún inversor. Las opiniones y objetivos son los publicados por la casa en la fecha "
         "de cada edición y pueden cambiar sin previo aviso. Las rentabilidades esperadas no garantizan rentabilidades "
         "futuras. Para cualquier decisión de inversión, consulte con su gestor.")
TEMPLATES = Path(__file__).resolve().parent / "templates"


# ------------------------------------------------------------------ gráficos
def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRIS,
                         "axes.labelcolor": TINTA, "xtick.color": TINTA, "ytick.color": TINTA})
    return plt


def chart_stances(a: EditionData, b: EditionData, changed: set[str], path: Path) -> Path:
    """Mapa de posturas: una fila por activo, una columna por edición; los activos que cambian, marcados."""
    plt = _plt()
    va, vb = {v.asset_id: v for v in a.views}, {v.asset_id: v for v in b.views}
    order = [aid for aid, _, _ in ASSETS] + sorted({*va, *vb} - {x for x, _, _ in ASSETS})
    rows = [aid for aid in order if (aid in va or aid in vb) and any(v.stance != "OTRA" for v in (va.get(aid), vb.get(aid)) if v)]
    h = 0.34 * len(rows) + 1.3
    fig, ax = plt.subplots(figsize=(8.6, h), dpi=150)
    ax.set_xlim(0, 2); ax.set_ylim(len(rows), 0); ax.axis("off")
    for i, aid in enumerate(rows):
        for j, v in enumerate((va.get(aid), vb.get(aid))):
            st = v.stance if v else None
            ax.add_patch(plt.Rectangle((j + 0.02, i + 0.08), 0.96, 0.84, color=STANCE_COLORS.get(st, "#ffffff"),
                                       ec="#ffffff" if v else GRIS, ls="-" if v else ":", lw=0.8))
            ax.text(j + 0.5, i + 0.52, (v.stance if v else "no figura"), ha="center", va="center", fontsize=7.3,
                    color=TINTA if v else GRIS)
        v = vb.get(aid) or va.get(aid)
        mark = f"v:{aid}" in changed
        ax.text(-0.03, i + 0.52, ("● " if mark else "") + v.label, ha="right", va="center", fontsize=8,
                color=ROJO if mark else TINTA, fontweight="bold" if mark else "normal")
    for j, ed in enumerate((a, b)):
        ax.text(j + 0.5, -0.35, ed.edition.label, ha="center", va="bottom", fontsize=10, fontweight="bold")
    fig.subplots_adjust(left=0.47, right=0.99, top=1 - 0.75 / h, bottom=0.02)
    fig.savefig(path, facecolor="white"); plt.close(fig)
    return path


def chart_targets(changes: list[Change], path: Path, unit: str, title: str) -> Path | None:
    """Objetivos revisados en la misma unidad: pb para rendimientos y diferenciales; % para índices, divisas y materias primas."""
    table = [c for c in changes if c.kind == "revision_objetivo" and not c.id.startswith("g:")]
    pool = table or [c for c in changes if c.kind in ("objetivo", "postura")]
    rows = sorted([c for c in pool if c.delta is not None and c.delta_unit == unit], key=lambda c: c.delta)
    if not rows:
        return None
    plt = _plt()
    h = 0.32 * len(rows) + 1.2
    fig, ax = plt.subplots(figsize=(8.6, h), dpi=150)
    ax.barh(range(len(rows)), [c.delta for c in rows], color=[ROJO if c.delta > 0 else GRIS for c in rows], height=0.62)
    ax.set_yticks(range(len(rows)), [f"{c.label}  ({c.before} → {c.after})" if c.kind == "revision_objetivo" else c.label for c in rows], fontsize=8)
    for i, c in enumerate(rows):
        ax.text(c.delta, i, f" {fmt_delta(c.delta, unit)} ", va="center", ha="left" if c.delta > 0 else "right", fontsize=8)
    ax.axvline(0, color=TINTA, lw=0.8)
    span = max(abs(c.delta) for c in rows) * 1.35
    ax.set_xlim(-span, span)
    ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", color=TINTA)
    ax.spines[["top", "right"]].set_visible(False); ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout(); fig.savefig(path, facecolor="white"); plt.close(fig)
    return path


# ------------------------------------------------------------------ montaje
def _data_uri(path: Path | str | None) -> str | None:
    p = Path(path) if path else None
    if not p or not p.exists():
        return None
    mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def _stance_class(text: str | None) -> str:
    if not text:
        return "none"
    head = text.split("(")[0].strip().upper().replace(" ", "")
    for k in ("NEUTRAL-SOBREPONDERAR", "NEUTRAL-INFRAPONDERAR", "SOBREPONDERAR", "INFRAPONDERAR", "NEUTRAL", "FAVORABLE", "NEGATIVO"):
        if head.startswith(k):
            return k
    return "none"


def _view(c: Change) -> dict:
    d = c.model_dump()
    d.update(s_before=_stance_class(c.before), s_after=_stance_class(c.after),
             delta_txt=fmt_delta(c.delta, c.delta_unit) if c.delta is not None else "", group_es=group_es(c.group))
    return d


def _edition_info(data: EditionData, role: str) -> dict:
    """Enlace al PDF: a la URL publicada si hay una ([opinion] pdf_url_base), si no al fichero local (sirve al equipo,
    que tiene la carpeta; un cliente externo verá la página citada y la cita literal, que es lo que importa)."""
    e = data.edition
    base = load_config().pdf_url_base
    uri = f"{base}/{e.path.name}" if base else e.path.resolve().as_uri()
    return {"role": role, "label": e.label, "date": e.date.strftime("%d-%m-%Y"), "file": e.path.name, "uri": uri}


def build(a: EditionData, b: EditionData, changes: list[Change], summary: str, out: Path, stats: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    changed = {c.id for c in changes if c.kind in ("postura", "nuevo", "desaparece", "objetivo")}
    pngs = {
        "stances": chart_stances(a, b, changed, out / "mapa_recomendaciones.png"),
        "pb": chart_targets(changes, out / "objetivos_pb.png", "pb", "Rendimientos y diferenciales objetivo revisados (pb)"),
        "pct": chart_targets(changes, out / "objetivos_pct.png", "%", "Objetivos de índices, divisas y materias primas (% de cambio)"),
    }
    stance = [c for c in changes if c.kind == "postura"]
    gone = [c for c in changes if c.kind == "desaparece"]
    gone_regions = {c.group for c in gone if not any(v.region == c.group for v in b.views)}
    headline = [{"text": f"{c.label}: {c.before} → {c.after}"} for c in stance]
    headline += [{"text": f"{r} deja de tener bloque propio de recomendaciones ({sum(c.group == r for c in gone)} activos)"} for r in sorted(gone_regions)]
    headline += [{"text": f"{c.label}: deja de figurar"} for c in gone if c.group not in gone_regions]
    headline += [{"text": f"{c.label}: se incorpora ({c.after})"} for c in changes if c.kind == "nuevo"]
    told = [c for c in changes if c.explanation]
    n_fact = sum(c.status == "factual" for c in told)
    n_llm = len(told) - n_fact                                 # las factuales no pasan por Jev: no cuentan como «no verificadas»
    n_ver = sum(c.status == "publicar" for c in told)
    table_rows = [c for c in changes if c.kind == "revision_objetivo" and not c.id.startswith("g:")]
    same = unchanged_views(a, b)
    same.sort(key=lambda x: REGION_ORDER.index(x[0]) if x[0] in REGION_ORDER else 99)
    verified_any = any(c.support is not None for c in told)
    ctx = {
        "brand": get_settings().brand, "title": f"Opinión Corporativa: qué cambia del {a.edition.label} al {b.edition.label}",
        "date": dt.date.today().strftime("%d-%m-%Y"), "editions": [_edition_info(a, "Edición anterior"), _edition_info(b, "Edición nueva")],
        "prev": _edition_info(a, ""), "curr": _edition_info(b, ""),
        "kpi": {"stance": len(stance), "targets": len(table_rows) or len([c for c in changes if c.kind == "objetivo"]),
                "trends": len([c for c in changes if c.kind in ("tendencia_nueva", "tendencia_sale", "tendencia_conclusion")]),
                "verified": f"{n_ver}/{n_llm}" if verified_any else f"{len(told)}",
                "verified_label": (f"frases verificadas por Jev · {n_fact} factuales" if verified_any
                                   else "frases, sin verificar (Jev no configurado)"),
                "why": sum(p["status"] in ("publicar", "sin verificar") for c in changes for p in c.rationale),
                "why_new": sum(bool(p.get("new")) for c in changes for p in c.rationale if p["status"] != "revisar")},
        "summary": summary, "headline": headline,
        "stance": [_view(c) for c in stance],
        "gone_new": [_view(c) for c in changes if c.kind in ("nuevo", "desaparece")],
        "targets": [_view(c) for c in changes if c.kind == "objetivo"],
        "groups": [_view(c) for c in changes if c.id.startswith("g:")],
        "table_rows": [_view(c) for c in table_rows],
        "table_image": _data_uri(b.table_image), "table_page": b.table_page,
        "trends": [_view(c) for c in changes if c.kind.startswith("tendencia")], "current_trends": [t.model_dump() for t in b.trends],
        "risks": [_view(c) for c in changes if c.kind == "riesgo"],
        "same": same, "charts": {k: _data_uri(p) for k, p in pngs.items()}, "stats": stats, "legal": LEGAL,
    }
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    html_path = out / "informe.html"
    html_path.write_text(env.get_template("informe.html").render(**ctx), encoding="utf-8")
    payload = {
        "ediciones": [{"label": e.edition.label, "fecha": str(e.edition.date), "fichero": e.edition.path.name, "md5": e.edition.md5} for e in (a, b)],
        "resumen": summary,
        "cambios": [c.model_dump(mode="json") for c in changes],
        "recomendaciones": {e.edition.label: [v.model_dump(mode="json") for v in e.views] for e in (a, b)},
        "tabla_sinoptica": {e.edition.label: [r.model_dump(mode="json") for r in e.targets] for e in (a, b)},
        "tendencias": {e.edition.label: [t.model_dump(mode="json") for t in e.trends] for e in (a, b)},
        "estadisticas": stats,
    }
    (out / "cambios.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"html": html_path, "json": out / "cambios.json", "png": [p for p in pngs.values() if p]}
