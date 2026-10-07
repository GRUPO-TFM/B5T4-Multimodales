"""
Paso 4 · Una frase por cambio, con la cita de la página, y doble control con Jev.

El LLM recibe los cambios ya calculados por Python y SOLO el texto que hace falta: la evidencia literal de cada
cambio y los párrafos macro de la página nueva (recortados). No decide qué ha cambiado: lo cuenta para un cliente.
Cada frase pasa después dos controles en UNA llamada a Jev:
  · support      ¿la evidencia respalda la frase?      (que no diga nada que no esté en el documento)
  · advice_risk  ¿suena a recomendación personalizada?  (el informe va a clientes: MiFID II)
Si una frase no pasa, se sustituye por la frase factual generada sin LLM («X pasa de A a B (p. N)»):
el informe nunca publica una frase que no se ha podido respaldar.

Coste: una llamada al LLM (≈ 6-8 k tokens de entrada) + una llamada a Jev por frase, en paralelo.
"""
from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from ...config import get_settings
from ...models import verifier
from .catalog import group_es, row_label
from .llmcall import Usage, ask_json, load_config
from .schemas import Change, EditionData


class _Item(BaseModel):
    id: str
    sentence: str = Field(..., description="una frase en español para un cliente, terminada con la cita «(p. N)»")


class _Out(BaseModel):
    summary: str = Field(..., description="3-4 frases: lo esencial de los cambios, para un cliente")
    items: list[_Item]


class _Rewrite(BaseModel):
    items: list[_Item]


REWRITE = """Estas frases para clientes de Andbank no han superado la verificación automática: el verificador no ha
encontrado respaldo suficiente en el texto fuente. Reescribe cada una (mismo id) ciñéndote SOLO a lo que dice el
TEXTO FUENTE que acompaña a cada una: sin motivos ni matices que no estén ahí, copiando posturas y cifras literales,
una frase, tono informativo, sin aconsejar al lector, terminada con la cita «(p. N)»."""


SYSTEM = """Redactas para CLIENTES de banca privada de Andbank un resumen de qué ha cambiado en la Opinión
Corporativa de la casa entre dos ediciones. Los cambios YA están calculados: no añadas ni quites ninguno.

Para cada cambio (id), UNA frase:
- Sujeto: «Andbank» (o, como mucho una de cada cuatro frases, «la casa»). No uses «la entidad», «la firma»,
  «el banco» ni «el documento»: alternar sujetos suena artificial.
- Di qué cambia y, si el CONTEXTO de la página lo explica, el motivo en pocas palabras.
- Termina con la cita de la página entre paréntesis: «(p. 5)». Usa la página indicada en el cambio.
- Copia las cifras tal y como vienen (5,00 %, 900 pb…). Escribe las posturas con la palabra completa y en
  mayúsculas, sin espacios alrededor del guion (SOBREPONDERAR, NEUTRAL-SOBREPONDERAR; no «SOBREPOND.»). No inventes cifras.
- Tono informativo y neutral. PROHIBIDO dirigirse al lector o aconsejarle: nada de «debería», «le recomendamos»,
  «es momento de comprar/vender», «conviene», «aproveche». Describe la visión de la casa, no la del lector.

summary: 3-4 frases que cuenten lo esencial (los cambios de postura primero), mismo tono y sin citas."""


def fallback(c: Change) -> str:
    """Frase factual sin LLM: lo que se publica si la del LLM no supera la verificación."""
    page = c.page_after or c.page_before
    cite = f" (p. {page})" if page else ""
    if c.id.startswith("g:"):
        g = group_es(c.group)
        return f"La casa revisa {c.before} de {g[:1].lower() + g[1:]}: {c.after}{cite}."
    if c.kind in ("nuevo", "tendencia_nueva"):
        return f"{c.label}: se incorpora con {c.after}{cite}."
    if c.kind in ("desaparece", "tendencia_sale"):
        return f"{c.label}: deja de figurar en la nueva edición (antes, {c.before}){cite}."
    return f"{c.label}: pasa de {c.before} a {c.after}{cite}."


def _gid(group: str) -> str:
    """Identificador sin espacios para el LLM («g:fixed-income-core-countries»): los ids con espacios se corrompen."""
    return "g:" + re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")


def group_revisions(changes: list[Change]) -> list[Change]:
    """Las revisiones de la tabla sinóptica se explican por bloque (una frase por clase de activo), no una a una."""
    by = defaultdict(list)
    for c in changes:
        if c.kind == "revision_objetivo":
            by[c.group].append(c)
    groups = []
    for g, cs in by.items():
        up, n = sum(c.direction == "al alza" for c in cs), len(cs)
        parts = [f"{up} al alza" if up else "", f"{n - up} a la baja" if n - up else ""]
        groups.append(Change(id=_gid(g), kind="revision_objetivo", group=g, label=f"Objetivos · {group_es(g)}",
                             before=f"{n} objetivo{'s' if n > 1 else ''}", after=" y ".join(p for p in parts if p),
                             page_after=cs[0].page_after, importance=2,
                             evidence_after="; ".join(f"{c.label} {c.before}→{c.after}" for c in cs),
                             checks=[f"✓ {sum(not ch.startswith('⚠') for c in cs for ch in c.checks)} filas con suma de control"]
                                    if any(c.checks for c in cs) else []))
    return groups


def _macro_context(page_text: str, limit: int = 2600) -> str:
    """Los párrafos macro de la página (antes del bloque de recomendaciones), recortados: ahí está el «porqué»."""
    t = re.sub(r"\s+", " ", page_text)
    i = t.lower().find("perspectivas de mercado")
    body = t[:i] if i > 0 else t
    body = re.sub(r"^.*?COYUNTURA MACROECON[ÓO]MICA\s*", "", body, count=1, flags=re.S)
    return body[:limit]


FACTUAL_KINDS = ("desaparece", "tendencia_sale", "nuevo")   # ausencias: ningún pasaje puede «respaldar» que algo ya no está


def _passage(c: Change, before: EditionData, after: EditionData) -> str:
    """Lo que Jev usa para juzgar la frase: la evidencia literal de las dos ediciones y, si la frase puede incluir
    un motivo, los párrafos macro de la página nueva (de ahí sale el «porqué» que redacta el modelo)."""
    parts = [f"{c.label}. Edición anterior ({before.edition.label}): {c.before or 'no figura'}. "
             f"Edición nueva ({after.edition.label}): {c.after or 'no figura'}."]
    if c.evidence_before:
        parts.append(f"Texto literal, edición anterior: {c.evidence_before}")
    if c.evidence_after:
        parts.append(f"Texto literal, edición nueva: {c.evidence_after}")
    if c.page_after and c.kind in ("postura", "objetivo", "riesgo", "tendencia_nueva", "tendencia_conclusion"):
        parts.append(f"Contexto de la página {c.page_after} (edición nueva): {_macro_context(after.pages.get(c.page_after, ''), 2500)}")
    return "\n\n".join(parts)


def _jev(sentence: str, passage: str) -> tuple[float | None, float | None]:
    """Respaldo y tono en UNA llamada (dos preguntas sobre el mismo estado). Un fallo de red se reintenta una vez;
    si persiste, la frase queda «sin verificar» (nunca se publica como verificada ni se tumba la ejecución)."""
    q = {"ok": {"type": "noul", "instructions": (
            "La AFIRMACIÓN está respaldada por el PASAJE FUENTE: se refiere al mismo concepto y periodo, y las cifras "
            "y posturas coinciden admitiendo redondeo razonable. Si el pasaje no lo menciona, NO está respaldada.")},
         "rec": {"type": "noul", "instructions": (
            "La AFIRMACIÓN constituye una recomendación de inversión personalizada o una incitación al lector a comprar "
            "o vender (en el sentido de MiFID II), y no mera información o descripción de la visión de una entidad.")}}
    for attempt in (1, 2):
        try:
            ans = verifier._ask(f"PASAJE FUENTE:\n{passage}\n\nAFIRMACIÓN:\n{sentence}", q)
            return round(ans["ok"]["noul"], 3), round(ans["rec"]["noul"], 3)
        except Exception as e:
            if attempt == 2:
                _JEV_ERRORS.append(str(e)[:120])
    return None, None


_JEV_ERRORS: list[str] = []
KEEP_MIN = 0.60   # por debajo de este respaldo, una frase del modelo no se enseña: se sustituye por la factual


def explain(changes: list[Change], before: EditionData, after: EditionData, usage: Usage | None = None,
            use_llm: bool = True, verify: bool = True, log=print) -> tuple[list[Change], str]:
    """Rellena explanation/support/advice_risk/status en cada cambio que se cuenta, y devuelve el resumen.
    use_llm=False / verify=False: frases factuales sin modelo y sin Jev (pruebas, o modo sin claves)."""
    s, cfg = get_settings(), load_config()
    told = [c for c in changes if c.kind != "revision_objetivo"] + group_revisions(changes)
    if not told:
        return changes, "No hay cambios entre las dos ediciones."
    factual = [c for c in told if c.kind in FACTUAL_KINDS]
    for c in factual:                                       # se cuentan con la frase factual: ni LLM ni Jev
        c.explanation, c.status = fallback(c), "factual"
    told = [c for c in told if c.kind not in FACTUAL_KINDS]

    lines = "\n".join(
        f"- id={c.id} | {c.kind} | {c.group} | {c.label} | antes: {c.before or '—'} | ahora: {c.after or '—'} "
        f"| página {c.page_after or c.page_before or '—'}" + (f"\n    fuente: {c.evidence_after}" if c.evidence_after else "")
        for c in told)
    pages = sorted({c.page_after for c in told if c.page_after and c.kind in ("postura", "objetivo", "nuevo", "tendencia_nueva", "riesgo")})
    context = "\n\n".join(f"[{after.edition.label} · página {n}]\n{_macro_context(after.pages.get(n, ''))}" for n in pages)
    user = (f"Edición anterior: {before.edition.label} ({before.edition.date:%d-%m-%Y}). "
            f"Edición nueva: {after.edition.label} ({after.edition.date:%d-%m-%Y}).\n\nCAMBIOS:\n{lines}\n\n"
            f"CONTEXTO (párrafos macro de la edición nueva):\n{context}")
    summary, sentences = "", {}
    if s.has_llm and use_llm:
        out = ask_json(_Out, SYSTEM, user, cfg.model_text, cfg.reasoning, usage, log=log)
        summary, sentences = out.summary.strip(), {i.id: i.sentence.strip() for i in out.items}
    else:
        log("  sin LLM: frases factuales sin redactar")
    for c in told:
        c.explanation = sentences.get(c.id) or fallback(c)

    def _verify(items: list[Change]) -> None:
        with ThreadPoolExecutor(max_workers=16) as ex:
            results = list(ex.map(lambda c: _jev(c.explanation, _passage(c, before, after)), items))
        for c, (sup, adv) in zip(items, results):
            c.support, c.advice_risk = sup, adv
            if adv is not None and adv >= 0.5:
                c.status, c.explanation = "sustituida (tono de recomendación)", fallback(c)
            elif sup is not None and sup < cfg.discard_threshold:
                c.status, c.explanation = "sustituida (sin respaldo)", fallback(c)
            elif any(ch.startswith("⚠") for ch in c.checks):
                pass                                          # «revisar» por una comprobación sin LLM: se mantiene
            elif sup is None:
                c.status = "sin verificar"                   # Jev no ha contestado: se enseña, pero sin marca de verificada
            else:
                c.status = "publicar" if sup >= cfg.publish_threshold else "revisar"

    if verifier.available() and verify:
        _verify(told)
        # Segunda oportunidad: lo que queda «a revisar» por falta de respaldo se reescribe pegado al texto fuente y
        # se vuelve a verificar (una llamada barata). Si sigue sin pasar, se queda marcado para revisión humana.
        weak = [c for c in told if c.status == "revisar" and c.support is not None and s.has_llm and use_llm]
        if weak:
            user = "\n\n".join(f"- id={c.id}\n  FRASE: {c.explanation}\n  TEXTO FUENTE: {_passage(c, before, after)[:1800]}" for c in weak)
            try:
                fixed = {i.id: i.sentence.strip() for i in ask_json(_Rewrite, REWRITE, user, cfg.model_text, cfg.reasoning, usage, log=log).items}
                for c in weak:
                    if fixed.get(c.id):
                        c.explanation = fixed[c.id]
                _verify(weak)
                log(f"  reescritas {len(weak)} frases flojas → {sum(c.status == 'publicar' for c in weak)} pasan ahora")
            except Exception as e:                            # la reescritura es opcional: nunca tumba el informe
                log(f"  reescritura omitida: {e}")
        for c in told:                                       # lo que sigue flojo tras la segunda oportunidad no va al cliente
            if c.status == "revisar" and c.support is not None and c.support < KEEP_MIN:
                c.status, c.explanation = "sustituida (respaldo insuficiente)", fallback(c)
        if _JEV_ERRORS:
            log(f"  Jev: {len(_JEV_ERRORS)} llamadas fallidas (p. ej. {_JEV_ERRORS[0]}); esas frases quedan sin verificar")
            _JEV_ERRORS.clear()
        if summary:
            facts = "\n".join(f"{c.label}: {c.before or '—'} → {c.after or '—'}" for c in told)
            sp, sa = _jev(summary, facts)
            if (sa is not None and sa >= 0.5) or (sp is not None and sp < cfg.discard_threshold):
                log(f"  resumen descartado por la verificación (respaldo {sp}, tono {sa})")
                summary = ""
        log(f"  Jev: {sum(c.status == 'publicar' for c in told)}/{len(told)} frases respaldadas · "
            f"{sum(c.status.startswith('sustituida') for c in told)} sustituidas · {sum(c.status == 'revisar' for c in told)} a revisar "
            f"· {len(factual)} factuales sin verificar")
        for c in told:
            if c.status != "publicar":
                log(f"     [{c.status} · respaldo {c.support} · tono {c.advice_risk}] {c.id}: {sentences.get(c.id, c.explanation)[:150]}")
    else:
        log("  Jev no configurado: frases sin verificar")
        for c in told:
            if c.status == "sin verificar" and c.explanation == fallback(c):
                c.status = "factual"                        # una frase factual generada por Python no necesita verificación

    told = told + factual
    by_id = {c.id: c for c in told}
    for c in changes:                                       # las revisiones sueltas heredan la frase de su bloque
        if c.kind == "revision_objetivo" and _gid(c.group) in by_id and c.status != "revisar":
            c.status = by_id[_gid(c.group)].status
    return changes + [c for c in told if c.id.startswith("g:")], summary
