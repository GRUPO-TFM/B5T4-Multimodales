"""
Paso 4b · El «porqué» de cada cambio importante, en palabras de la casa.

El informe no solo dice que el UST10 pasa a SOBREPONDERAR: dice por qué lo hace Andbank. Ese porqué está en los
párrafos macro de la página del país (y, para las tendencias, en el propio bloque). Cómo se extrae sin inventar:
  1. el LLM recibe el texto de cada página implicada UNA sola vez (con la lista de cambios que se justifican en
     ella) y, para dar contexto, el párrafo equivalente de la edición anterior; devuelve 2-4 argumentos por cambio,
     cada uno con una CITA LITERAL de la edición nueva que lo sostiene, y señala si el argumento es nuevo respecto
     a la edición anterior (qué ha cambiado en el discurso de la casa, no solo en la cifra);
  2. Python comprueba que la cita está de verdad en la página (si el modelo la ha retocado, se descarta) y que el
     mismo argumento no se repite en dos cambios de la misma página;
  3. Jev mide si el argumento está respaldado por su cita y su párrafo; lo que no pasa no se publica.
Así cada «porqué» del informe lleva su frase original al lado, y el cliente puede comprobarlo.
"""
from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from ...config import get_settings
from ...models import verifier
from .explain import _macro_context
from .llmcall import Usage, ask_json, load_config
from .schemas import Change, EditionData

MIN_PB = 25          # un objetivo revisado en ≥ 25 pb merece explicación; los retoques menores, no
SHOW_MIN = 0.60      # respaldo mínimo para enseñar un argumento (entre esto y publish_threshold, con marca «a revisar»)


class _Point(BaseModel):
    point: str = Field(..., description="argumento de la casa, una frase de 12-24 palabras, en tercera persona, sin interpretar")
    quote: str = Field(..., description="cita LITERAL del texto de la EDICIÓN NUEVA (copiada tal cual, 60-240 caracteres) que lo sostiene")
    new: bool = Field(False, description="true si este argumento NO aparecía en el texto de la edición anterior (es un cambio de discurso)")


class _Why(BaseModel):
    id: str
    points: list[_Point]


class _Out(BaseModel):
    items: list[_Why]


SYSTEM = """Te doy, página a página, el TEXTO de la edición NUEVA de la Opinión Corporativa de Andbank, la lista de
cambios que se justifican en esa página y, como contexto, el texto equivalente de la edición ANTERIOR.
Devuelve, por cambio (id), de 2 a 4 argumentos que expliquen POR QUÉ la casa toma esa posición, en palabras
sencillas para un cliente, cada uno con una CITA LITERAL del texto de la edición NUEVA (copiada carácter a
carácter, 60-240 caracteres, sin resumir ni corregir) que lo sostenga.
- Solo argumentos que estén en el texto nuevo. Si no justifica el cambio, devuelve una lista vacía para ese id.
- Cada argumento: UNA frase de 12 a 24 palabras que reformule la cita con sus mismas ideas y cifras, sin añadir
  conclusiones, causas ni matices que la cita no diga (un verificador automático comparará frase y cita).
- new=true cuando el argumento no estaba en el texto de la edición anterior (la casa ha cambiado de discurso, no
  solo de cifra). Da prioridad a esos: son los que explican el cambio. new=false si ya lo decía antes.
- Si varios cambios comparten página, no repitas un argumento en dos ids: asígnalo al cambio al que más atañe.
- Tono informativo; nunca aconsejes al lector. No repitas el cambio en sí (ya se sabe): explica el razonamiento
  (inflación, tipos, resultados, valoración, flujos…)."""


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9%]+", " ", t).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """¿Está la cita en la página? Se exige que el 85 % de sus ventanas de 6 palabras aparezcan en el texto."""
    q, t = _norm(quote).split(), _norm(text)
    if len(q) < 6:
        return " ".join(q) in t
    grams = [" ".join(q[i:i + 6]) for i in range(len(q) - 5)]
    return sum(g in t for g in grams) / len(grams) >= 0.85


def _around(quote: str, text: str, pad: int = 450) -> str:
    """El párrafo alrededor de la cita: Jev juzga mejor con contexto que con 200 caracteres sueltos."""
    flat = re.sub(r"\s+", " ", text)
    head = re.sub(r"\s+", " ", quote)[:40]
    i = flat.find(head)
    if i < 0:
        return quote
    return flat[max(0, i - pad): i + len(quote) + pad]


def candidates(changes: list[Change]) -> list[Change]:
    out = []
    for c in changes:
        if c.kind in ("postura", "tendencia_nueva", "tendencia_conclusion", "riesgo"):
            out.append(c)
        elif c.kind == "objetivo" and ((c.delta is not None and c.delta_unit == "pb" and abs(c.delta) >= MIN_PB)
                                       or c.delta_unit in ("%", "nivel", "tipo de cambio") or c.delta is None):
            out.append(c)
    return [c for c in out if c.page_after]


def _page_text(c: Change, after: EditionData) -> str:
    txt = after.pages.get(c.page_after, "")
    if c.kind.startswith("tendencia"):
        return txt[:6000]                                    # el bloque de tendencias es la propia argumentación
    return _macro_context(txt, 4500)


def _previous_text(c: Change, before: EditionData, limit: int = 2200) -> str:
    """El párrafo macro de la MISMA región en la edición anterior: con él, el modelo sabe qué argumentos son nuevos."""
    if not c.page_before or c.kind.startswith("tendencia"):
        return ""
    txt = before.pages.get(c.page_before, "")
    return _macro_context(txt, limit)


def _blocks(cands: list[Change], before: EditionData, after: EditionData) -> str:
    """Un bloque por PÁGINA (no por cambio): la misma página no se envía tres veces, y el modelo ve juntos los
    cambios que comparten argumentación (core y periferia europea, México local y en dólares…)."""
    by_page: dict[int, list[Change]] = {}
    for c in cands:
        by_page.setdefault(c.page_after, []).append(c)
    out = []
    for page, cs in sorted(by_page.items()):
        heads = "\n".join(f"- id={c.id} · {c.label}: {c.before or '—'} → {c.after or '—'}" for c in cs)
        prev = next((_previous_text(c, before) for c in cs if _previous_text(c, before)), "")
        block = f"### Página {page} de la edición nueva ({after.edition.label})\nCAMBIOS que se justifican aquí:\n{heads}\n\nTEXTO NUEVO:\n{_page_text(cs[0], after)}"
        if prev:
            block += f"\n\nTEXTO EQUIVALENTE DE LA EDICIÓN ANTERIOR ({before.edition.label}), solo como contexto (no cites de aquí):\n{prev}"
        out.append(block)
    return "\n\n".join(out)


def add_rationale(changes: list[Change], before: EditionData, after: EditionData, usage: Usage | None = None,
                  use_llm: bool = True, verify: bool = True, log=print) -> int:
    """Rellena c.rationale (lista de {point, quote, page, new, contexto, support, status}) en los cambios importantes.
    Devuelve cuántos puntos se publican."""
    s, cfg = get_settings(), load_config()
    cands = candidates(changes)
    if not cands or not (s.has_llm and use_llm):
        log("  porqué: sin LLM, se omite")
        return 0
    out = ask_json(_Out, SYSTEM, _blocks(cands, before, after), cfg.model_text, cfg.reasoning, usage, log=log)
    by_id = {w.id: w.points for w in out.items}
    dropped, dup, seen_quotes = 0, 0, set()
    for c in cands:
        pts = []
        page_txt = after.pages.get(c.page_after, "")
        for p in by_id.get(c.id, [])[:4]:
            if not quote_in_text(p.quote, page_txt):
                dropped += 1
                continue
            key = (c.page_after, _norm(p.quote)[:60])
            if key in seen_quotes:                            # misma cita en dos cambios de la misma página: una vez
                dup += 1
                continue
            seen_quotes.add(key)
            ctx = _around(p.quote, page_txt)
            pts.append({"point": p.point.strip(), "quote": p.quote.strip(), "page": c.page_after, "new": bool(p.new),
                        "contexto": _around(p.quote, page_txt, 220), "support": None, "status": "sin verificar", "context": ctx})
        c.rationale = pts
    flat = [(c, p) for c in cands for p in c.rationale]
    if flat and verifier.available() and verify:
        def check(cp):
            c, p = cp
            for _ in (1, 2):                                  # un fallo de red se reintenta; si persiste, «sin verificar»
                try:
                    return verifier.supports(p["point"], f"{c.label}: {c.before or '—'} → {c.after or '—'}.\n{p['context']}")
                except Exception:
                    pass
            return None
        with ThreadPoolExecutor(max_workers=16) as ex:
            sups = list(ex.map(check, flat))
        for (c, p), sup in zip(flat, sups):
            p["support"] = sup
            p["status"] = ("sin verificar" if sup is None else "publicar" if sup >= cfg.publish_threshold
                           else "descartado" if sup < SHOW_MIN else "revisar")
        for c in cands:
            c.rationale = [p for p in c.rationale if p["status"] != "descartado"]
    for c in cands:
        for p in c.rationale:
            p.pop("context", None)
    published = sum(p["status"] in ("publicar", "sin verificar") for c in cands for p in c.rationale)
    n_new = sum(p["new"] for c in cands for p in c.rationale if p["status"] in ("publicar", "sin verificar"))
    log(f"  porqué: {len(cands)} cambios explicados · {published} argumentos con cita literal publicados ({n_new} nuevos respecto a la edición anterior) · "
        f"{dropped} citas descartadas por no estar en el texto · {dup} repetidas · {sum(p['status'] == 'revisar' for c in cands for p in c.rationale)} a revisar "
        f"(respaldo {SHOW_MIN:.0%}-{cfg.publish_threshold:.0%}); por debajo de {SHOW_MIN:.0%} no se publican")
    return published
