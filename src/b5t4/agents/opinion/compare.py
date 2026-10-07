"""
Paso 3 · Comparación determinista entre dos ediciones. Aquí NO hay LLM.

Por qué: un cambio de recomendación no puede «alucinarse». O sale de cruzar las dos tablas extraídas, o no existe.
El LLM solo interviene después, para explicar con una frase un cambio que Python ya ha encontrado.

Qué se compara:
  · recomendaciones por activo (mismo identificador del catálogo): postura, objetivo, activo nuevo o que desaparece;
  · tabla sinóptica (por nombre de fila): objetivo revisado, en puntos básicos o en %;
  · tendencias estructurales (por tema): tema nuevo, tema que sale, conclusión que cambia de signo;
  · riesgos del oro: cambio de calificación.
"""
from __future__ import annotations

import re
import unicodedata

from .catalog import TABLE_MAP, fmt_es, row_label
from .schemas import STANCE_ORDER, Change, EditionData

# Riesgo del oro: escala para saber si sube o baja
RISK_ORDER = ["BAJO", "BAJO-MEDIO", "MEDIO", "MEDIO-ALTO", "ALTO"]
POLARITY = {"POSITIVA": 1, "POSITIVO": 1, "FAVORABLE": 1, "NEUTRAL": 0, "NEGATIVA": -1, "NEGATIVO": -1, "DESFAVORABLE": -1}


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", (t or "").lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _nums(t: str | None) -> list[float]:
    """Las cifras de un objetivo, para saber si ha cambiado aunque cambie el texto de alrededor («rend.» / «rendimiento»)
    o el formato («4,5 %» = «4,50%»). Los puntos de miles se quitan antes: «1.600» → 1600."""
    if not t:
        return []
    t = re.sub(r"(?<=\d)\s+(?=[.,]\d)", "", t)                       # «18 ,50» (PDF en columnas) → «18,50»
    t = re.sub(r"(?<![\d.,])(?:19|20)\d{2}(?![\d.,%])", " ", t)       # «cierre de 2026: 1.600»: el año no es un objetivo
    t = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", t).replace(",", ".")    #   (un nivel se escribe «2.050», con punto de miles)
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]


def _stance_dir(a: str, b: str) -> str:
    if a in STANCE_ORDER and b in STANCE_ORDER:
        d = STANCE_ORDER.index(b) - STANCE_ORDER.index(a)
        return "mejora" if d > 0 else ("empeora" if d < 0 else "neutro")
    return "neutro"


def _fmt_view(v) -> str:
    """Postura y objetivo tal como se enseñan. Para un activo con solo objetivo (petróleo: stance OTRA) se enseña el
    objetivo una vez; y nunca la regla operativa del PDF («comprar por debajo de…»): el informe va a clientes."""
    target = re.sub(r"\s*\([^()]*\b(?:comprar|vender)\b[^()]*\)", "", v.target_raw or "", flags=re.I).strip()
    if v.stance == "OTRA" and target:
        return target
    return v.stance_raw.strip() + (f" ({target})" if target else "")


def compare_views(a: EditionData, b: EditionData) -> list[Change]:
    va, vb = {v.asset_id: v for v in a.views}, {v.asset_id: v for v in b.views}
    out: list[Change] = []
    for aid in list(va) + [k for k in vb if k not in va]:
        x, y = va.get(aid), vb.get(aid)
        if aid.startswith("otro:") and not (x and y):     # fuera de catálogo: solo se compara si sale en las dos
            continue
        if x and not y:
            out.append(Change(id=f"v:{aid}", kind="desaparece", group=x.region, label=x.label, before=_fmt_view(x),
                              page_before=x.page, importance=2))
            continue
        if y and not x:
            out.append(Change(id=f"v:{aid}", kind="nuevo", group=y.region, label=y.label, after=_fmt_view(y),
                              page_after=y.page, importance=2))
            continue
        stance_changed = x.stance != y.stance
        target_changed = _nums(x.target_raw) != _nums(y.target_raw)
        if not (stance_changed or target_changed):
            continue
        delta, unit = None, y.target_unit
        if x.target_value is not None and y.target_value is not None and x.target_value != y.target_value:
            delta = y.target_value - x.target_value
            if (y.target_unit or "").strip() == "%":           # rendimientos: el cambio se lee mejor en pb
                delta, unit = round(delta * 100), "pb"
            else:
                delta = round(delta, 4)
        if stance_changed:
            out.append(Change(id=f"v:{aid}", kind="postura", group=y.region, label=y.label, before=_fmt_view(x),
                              after=_fmt_view(y), direction=_stance_dir(x.stance, y.stance), delta=delta,
                              delta_unit=unit, page_before=x.page, page_after=y.page, importance=1))
        else:
            if delta is not None:
                direction = "al alza" if delta > 0 else "a la baja"
            else:                                           # varios objetivos en la misma línea (periferia, LatAm)
                xs, ys = _nums(x.target_raw), _nums(y.target_raw)
                ups = [b_ > a_ for a_, b_ in zip(xs, ys) if b_ != a_] if len(xs) == len(ys) else []
                direction = "al alza" if ups and all(ups) else ("a la baja" if ups and not any(ups) else "neutro")
            out.append(Change(id=f"v:{aid}", kind="objetivo", group=y.region, label=y.label, before=_fmt_view(x),
                              after=_fmt_view(y), direction=direction, delta=delta, delta_unit=unit,
                              page_before=x.page, page_after=y.page, importance=2))
    return out


def row_key(index: str) -> str:
    """Nombre de fila de la tabla sinóptica comparable entre ediciones. La columna es estrecha y el PDF corta los
    sufijos de forma distinta cada trimestre («(local)», «(loc», «(l»): se quitan. «(Loc)» y «(USD)» de LatAm se
    conservan, porque distinguen dos bonos distintos."""
    k = _norm(index)
    if re.search(r"\b10yr gov bond\b", k):
        k = re.sub(r"\s+(local|loca|loc|lo|l)$", "", k)
    return k


def _rate_like(asset_class: str, index: str) -> bool:
    t = _norm(asset_class + " " + index)
    return "fixed income" in t or "bond" in t or "govie" in t or "credit" in t


def compare_targets(a: EditionData, b: EditionData) -> list[Change]:
    ta = {row_key(r.index): r for r in a.targets}
    out = []
    page = next((k for k, t in b.pages.items() if "TABLA SIN" in t.upper()), None)
    for r in b.targets:
        old = ta.get(row_key(r.index))
        if not old or old.target is None or r.target is None or abs(old.target - r.target) < 1e-9:
            continue
        rate = _rate_like(r.asset_class, r.index) and "credit" not in _norm(r.asset_class + " " + r.index)
        if _rate_like(r.asset_class, r.index):
            credit = "credit" in _norm(r.asset_class + " " + r.index)
            delta = round(r.target - old.target) if credit else round((r.target - old.target) * 100)
            unit = "pb"
        else:
            delta, unit = round((r.target / old.target - 1) * 100, 1), "%"
        out.append(Change(id=f"t:{row_key(r.index)}", kind="revision_objetivo", group=r.asset_class, label=row_label(r.index),
                          before=fmt_es(old.target, rate=rate), after=fmt_es(r.target, rate=rate), delta=delta, delta_unit=unit,
                          direction="al alza" if r.target > old.target else "a la baja", page_after=page, importance=3))
    return out


def _similar(x: str, y: str) -> float:
    a, b = set(_norm(x).split()) - {"de", "la", "las", "el", "los", "del", "sector", "y"}, set(_norm(y).split()) - {"de", "la", "las", "el", "los", "del", "sector", "y"}
    return len(a & b) / max(1, len(a | b))


def _polarity(conclusion: str) -> int | None:
    head = _norm(conclusion).upper().split()
    return POLARITY.get(head[0]) if head else None


def compare_trends(a: EditionData, b: EditionData) -> list[Change]:
    out, matched = [], set()
    for t in b.trends:
        best = max(a.trends, key=lambda o: _similar(o.title, t.title), default=None)
        if best is not None and _similar(best.title, t.title) >= 0.4:
            matched.add(id(best))
            if _polarity(best.conclusion) != _polarity(t.conclusion):
                out.append(Change(id=f"tr:{_norm(t.title)[:40]}", kind="tendencia_conclusion", group="Tendencias estructurales",
                                  label=t.title, before=best.conclusion, after=t.conclusion, page_before=best.page,
                                  page_after=t.page, importance=2))
        else:
            out.append(Change(id=f"tr:{_norm(t.title)[:40]}", kind="tendencia_nueva", group="Tendencias estructurales",
                              label=t.title, after=t.conclusion, page_after=t.page, importance=2))
    for o in a.trends:
        if id(o) not in matched:
            out.append(Change(id=f"tr:{_norm(o.title)[:40]}", kind="tendencia_sale", group="Tendencias estructurales",
                              label=o.title, before=o.conclusion, page_before=o.page, importance=3))
    return out


def compare_risks(a: EditionData, b: EditionData) -> list[Change]:
    out = []
    for r in b.gold_risks:
        old = max(a.gold_risks, key=lambda o: _similar(o.risk, r.risk), default=None)
        if old is None or _similar(old.risk, r.risk) < 0.3 or _norm(old.level) == _norm(r.level):
            continue
        lv = lambda s: RISK_ORDER.index(s.upper().strip()) if s.upper().strip() in RISK_ORDER else None
        d = (lv(r.level) or 0) - (lv(old.level) or 0)
        out.append(Change(id=f"r:{_norm(r.risk)[:40]}", kind="riesgo", group="Oro", label=f"Riesgo para el oro: {r.risk}",
                          before=old.level, after=r.level, direction="al alza" if d > 0 else "a la baja",
                          page_before=old.page, page_after=r.page, importance=2))
    return out


def cross_check(data: EditionData) -> dict[str, str]:
    """Para cada recomendación con objetivo numérico, ¿dice lo mismo la tabla sinóptica de la misma edición?
    Devuelve asset_id → «coincide» / «difiere (texto X · tabla Y)» y lo anota en cada View."""
    rows = {row_key(r.index): r for r in data.targets}
    out = {}
    for v in data.views:
        spec = TABLE_MAP.get(v.asset_id)
        if not spec or v.target_value is None:
            continue
        r = rows.get(spec[0])
        if r is None or r.target is None:
            continue
        tol = {"rate": 0.011, "spread": 1.0, "level": max(0.011, abs(r.target) * 0.002)}[spec[1]]
        ok = abs(r.target - v.target_value) <= tol
        v.table_check = "coincide" if ok else f"difiere (texto {fmt_es(v.target_value)} · tabla {fmt_es(r.target)})"
        out[v.asset_id] = v.table_check
    return out


def _annotate(changes: list[Change], a: EditionData, b: EditionData) -> list[Change]:
    """Evidencia literal y comprobaciones (sin LLM) de cada cambio; «revisar» si algo no cuadra."""
    va, vb = {v.asset_id: v for v in a.views}, {v.asset_id: v for v in b.views}
    rb = {row_key(r.index): r for r in b.targets}
    for c in changes:
        if c.id.startswith("v:"):
            aid = c.id[2:]
            x, y = va.get(aid), vb.get(aid)
            c.evidence_before, c.evidence_after = (x.evidence if x else None), (y.evidence if y else None)
            for v, tag in ((x, a.edition.label), (y, b.edition.label)):
                if v is None:
                    continue
                if v.evidence is None:
                    c.checks.append(f"⚠ sin línea literal en el PDF ({tag})")
                if v.table_check:
                    c.checks.append(("✓ " if v.table_check == "coincide" else "⚠ ") + f"tabla sinóptica {tag}: {v.table_check}")
        elif c.id.startswith("t:"):
            r = rb.get(c.id[2:])
            if r is not None and r.consistent is not None:
                c.checks.append("✓ suma de control: rentabilidad esperada = objetivo/precio − 1"
                                if r.consistent else "⚠ suma de control fallida: revisar la lectura de la fila")
        elif c.id.startswith("tr:"):
            t_after = next((t for t in b.trends if _norm(t.title)[:40] == c.id[3:]), None)
            t_before = next((t for t in a.trends if _norm(t.title)[:40] == c.id[3:]), None)
            c.evidence_after = t_after.evidence if t_after else None
            c.evidence_before = t_before.evidence if t_before else None
            if (t_after and not t_after.evidence) or (t_before and not t_before.evidence):
                c.checks.append("⚠ no se ha localizado la frase de conclusión en el PDF")
        if any(ch.startswith("⚠") for ch in c.checks):
            c.status = "revisar"
    return changes


def compare(a: EditionData, b: EditionData) -> list[Change]:
    """Todos los cambios entre la edición `a` (anterior) y `b` (nueva), en orden de importancia."""
    cross_check(a); cross_check(b)
    changes = compare_views(a, b) + compare_trends(a, b) + compare_risks(a, b) + compare_targets(a, b)
    return sorted(_annotate(changes, a, b), key=lambda c: c.importance)


def unchanged_views(a: EditionData, b: EditionData) -> list[tuple[str, str, str]]:
    """(región, activo, postura) de lo que NO cambia: el cliente también quiere saber qué se mantiene."""
    va = {v.asset_id: v for v in a.views}
    return [(v.region, v.label, v.stance_raw) for v in b.views
            if v.asset_id in va and va[v.asset_id].stance == v.stance and _nums(va[v.asset_id].target_raw) == _nums(v.target_raw)]
