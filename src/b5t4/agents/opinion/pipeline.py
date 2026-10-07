"""
AGENTE 2 · ¿Qué ha cambiado en la visión de la casa? (Opinión Corporativa de Andbank)

    uv run b5t4 opinion                 → out/opinion/<fecha-hora>/ informe.html · cambios.json · *.png
    uv run b5t4 opinion --referencia    → lo mismo sin LLM en la lectura (extracción de referencia), para probar
    uv run b5t4 opinion --eval          → ¿lee bien el LLM los PDF? aciertos frente a la referencia

Flujo (cada paso en su módulo):
  1. select.latest_two()        sin LLM   manifiesto + portada + fecha del nombre → las dos últimas ediciones
  2. extract.extract_edition()  LLM       por edición y en paralelo: una llamada corta por página de recomendaciones
                                          (región ya detectada), una para tendencias y materias primas, y una de
                                          visión para la tabla sinóptica (imagen). Python busca luego la evidencia
                                          literal de cada dato y comprueba la tabla. Se guarda: un PDF se lee una vez.
  3. compare.compare()          sin LLM   diff determinista activo por activo + cruce texto ↔ tabla sinóptica
  4. explain.explain()          LLM+Jev   una frase por cambio con la página; Jev comprueba respaldo y tono (MiFID)
  5. report.build()             sin LLM   HTML para clientes con la fuente de cada dato, PNG y cambios.json
  4b. rationale.add_rationale() LLM+Jev   el porqué de cada cambio importante con cita literal (en paralelo con 4)
  6. video.make_video()         TTS       vídeo de ≤ 2 min montado con las frases ya verificadas (opcional, --video)

Fiabilidad, coste y latencia (medidos aquí con la extracción de referencia; el LLM real se mide con --eval):
  · todo lo que puede hacer Python lo hace Python: selección, comparación, evidencias, sumas de control, maquetación;
  · el LLM lee bloques cortos y con región conocida, sin razonamiento, y cada lectura se guarda (coste solo la primera vez);
  · ninguna frase se publica sin pasar por Jev o sin ser una frase factual generada por código.
"""
from __future__ import annotations

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ...config import get_settings
from .compare import compare
from .explain import explain
from .extract import extract_edition, load_reference
from .llmcall import Usage, load_config
from .rationale import add_rationale
from .report import build
from .select import latest_two, list_editions  # noqa: F401  (list_editions: lo usa la interfaz)


def run(out_root: Path | None = None, use_cache: bool = True, reference: bool = False, log=print) -> Path:
    """reference=True: usa la extracción de referencia (evals/opinion_referencia.json) en lugar del LLM en el paso 2."""
    s = get_settings()
    t0 = time.perf_counter()
    out = (out_root or s.out_dir / "opinion") / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    a_ed, b_ed = latest_two(log)
    log(f"1 ediciones: {a_ed.label} ({a_ed.date}) → {b_ed.label} ({b_ed.date})")

    t1 = time.perf_counter()
    if reference:
        log("2 extracción: REFERENCIA (evals/opinion_referencia.json), sin LLM")
        a, b = load_reference(a_ed), load_reference(b_ed)
        if a is None or b is None:
            raise RuntimeError("La referencia no cubre estas dos ediciones.")
    else:
        log("2 extracción")
        with ThreadPoolExecutor(max_workers=2) as ex:
            fa, fb = ex.submit(extract_edition, a_ed, use_cache, log), ex.submit(extract_edition, b_ed, use_cache, log)
            a, b = fa.result(), fb.result()

    t2 = time.perf_counter()
    changes = compare(a, b)
    kinds: dict[str, int] = {}
    for c in changes:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    cross = sum(1 for v in a.views + b.views if v.table_check == "coincide")
    cross_bad = [f"{v.asset_id} ({v.table_check})" for v in a.views + b.views if v.table_check and v.table_check != "coincide"]
    log(f"3 comparación: {len(changes)} cambios · {kinds} · cruce texto↔tabla: {cross} coinciden"
        + (f", {len(cross_bad)} difieren: {cross_bad}" if cross_bad else ""))

    t3 = time.perf_counter()
    log("4 explicación y verificación")
    usage = Usage(load_config())
    # La frase de cada cambio (explain) y su porqué (add_rationale) son independientes: una llamada al LLM cada
    # una más sus verificaciones. En paralelo el paso tarda lo que la más lenta, no la suma.
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_exp = ex.submit(explain, changes, a, b, usage=usage, log=log)
        f_why = ex.submit(add_rationale, changes, a, b, usage=usage, log=log)
        n_why = f_why.result()
        changes, summary = f_exp.result()
    told = [c for c in changes if c.explanation]
    if any(c.support is not None for c in told):
        verified = (f"{sum(c.status == 'publicar' for c in told)} de {len(told)} frases respaldadas por su fuente según Jev; "
                    f"{sum(c.status.startswith('sustituida') for c in told)} sustituidas por su versión factual; "
                    f"{sum(c.status == 'revisar' for c in told)} marcadas a revisar")
    elif s.has_llm:
        verified = f"{len(told)} frases redactadas por el modelo, sin verificar (Jev no configurado)"
    else:
        verified = f"{len(told)} frases factuales generadas sin modelo de lenguaje"

    t4 = time.perf_counter()
    paid = [d.usage for d in (a, b) if d.usage and not d.usage.get("cached")]      # lo guardado no se paga otra vez
    cost = usage.summary()["coste_usd"] + sum(u.get("coste_usd", 0) for u in paid)
    tokens_in = usage.summary()["tokens_entrada"] + sum(u.get("tokens_entrada", 0) for u in paid)
    tokens_out = usage.summary()["tokens_salida"] + sum(u.get("tokens_salida", 0) for u in paid)
    cached = [d.edition.label for d in (a, b) if d.usage.get("cached")]
    secs = {"extraccion": round(t2 - t1, 1), "comparacion": round(t3 - t2, 2), "explicacion": round(t4 - t3, 1)}
    stats = {"extraccion": "extracción de referencia, sin LLM" if reference else "modelo de lenguaje, bloques por página",
             "views_a": len(a.views), "views_b": len(b.views), "rows_a": len(a.targets), "rows_b": len(b.targets),
             "cross": f"{cross} objetivos coinciden" + (f", {len(cross_bad)} difieren" if cross_bad else ", ninguno difiere"),
             "verified": verified, "rationale": n_why, "tokens": {"entrada": tokens_in, "salida": tokens_out,
                                                                  "razonamiento": usage.summary()["tokens_razonamiento"]}, "coste_usd": round(cost, 4),
             "cost": f"{tokens_in:,} + {tokens_out:,} tokens ≈ {cost:.3f} $".replace(",", ".")
                     + (f" (lectura de {' y '.join(cached)} reutilizada, ya pagada)" if cached else ""), "segundos": secs}
    secs["total"] = round(time.perf_counter() - t0, 1)
    stats["time"] = f"{secs['total']} s hasta el informe (lectura {secs['extraccion']} s · explicación {secs['explicacion']} s)"
    files = build(a, b, changes, summary, out, stats)
    log(f"5 informe: {files['html']}")
    log(f"   {stats['cost']} · {stats['time']}")
    return out
