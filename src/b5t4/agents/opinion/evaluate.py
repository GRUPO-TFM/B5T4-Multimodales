"""
¿Lee bien el LLM los PDF? Compara la extracción con LLM (paso 2) con la extracción de referencia hecha a mano
(evals/opinion_referencia.json) y da la cifra de aciertos por bloque. Es la prueba que hay que pasar antes de
fiarse del informe: si la extracción falla, la comparación compara datos falsos.

    uv run b5t4 opinion --eval
"""
from __future__ import annotations

from .compare import _nums, _norm, row_key
from .extract import extract_edition, load_reference
from .select import latest_two


def score(llm, ref) -> dict:
    rv = {v.asset_id: v for v in ref.views}
    lv = {v.asset_id: v for v in llm.views if v.asset_id in rv or v.asset_id.startswith("otro:")}
    found = [a for a in rv if a in lv]
    stance_ok = [a for a in found if lv[a].stance == rv[a].stance]
    target_ok = [a for a in found if _nums(lv[a].target_raw) == _nums(rv[a].target_raw)]
    extra = [v.asset_id for v in llm.views if v.asset_id not in rv and v.asset_id not in ("oil", "gold")]
    rt = {row_key(r.index): r for r in ref.targets}
    lt = {row_key(r.index): r for r in llm.targets}
    rows = [k for k in rt if k in lt]
    rows_ok = [k for k in rows if lt[k].target is not None and abs(lt[k].target - rt[k].target) < 1e-6]
    tr_ok = sum(any(_norm(t.conclusion).split()[:1] == _norm(r.conclusion).split()[:1] for t in llm.trends) for r in ref.trends)
    return {
        "recomendaciones encontradas": f"{len(found)}/{len(rv)}",
        "postura correcta": f"{len(stance_ok)}/{len(found)}",
        "objetivo correcto": f"{len(target_ok)}/{len(found)}",
        "activos de más (no están en la referencia)": extra,
        "filas de la tabla sinóptica encontradas": f"{len(rows)}/{len(rt)}",
        "objetivo de la tabla correcto": f"{len(rows_ok)}/{len(rows)}",
        "tendencias (conclusión)": f"{tr_ok}/{len(ref.trends)}",
        "recomendaciones con evidencia literal en el PDF": f"{sum(v.evidence is not None for v in llm.views)}/{len(llm.views)}",
        "filas de la tabla con suma de control superada": f"{sum(r.consistent is True for r in llm.targets)}/{sum(r.consistent is not None for r in llm.targets)} comprobables",
        "cruce texto ↔ tabla": f"{sum(v.table_check == 'coincide' for v in llm.views)} coinciden · {sum(bool(v.table_check) and v.table_check != 'coincide' for v in llm.views)} difieren",
        "errores": [f"{a}: {lv[a].stance} {lv[a].target_raw} ≠ {rv[a].stance} {rv[a].target_raw}"
                    for a in found if a not in stance_ok or a not in target_ok]
                   + [f"tabla {k}: {lt[k].target} ≠ {rt[k].target}" for k in rows if k not in rows_ok]
                   + [f"falta {a}" for a in rv if a not in lv]
                   + [f"suma de control: {r.index} precio {r.current} objetivo {r.target} esperada {r.expected_perf} % "
                      f"(calculada {((r.target / r.current - 1) * 100):.1f} %)" for r in llm.targets if r.consistent is False],
    }


def run_eval(use_cache: bool = True, log=print) -> dict:
    out = {}
    for ed in latest_two(log):
        ref = load_reference(ed)
        if ref is None:
            log(f"{ed.label}: sin referencia")
            continue
        data = extract_edition(ed, use_cache, log)
        from .compare import cross_check
        cross_check(data)
        res = score(data, ref)
        res["coste de la lectura"] = f"{data.usage.get('tokens_entrada', 0)}+{data.usage.get('tokens_salida', 0)} tokens ≈ {data.usage.get('coste_usd', 0)} $"
        out[ed.label] = res
        log(f"\n{ed.label}")
        for k, v in res.items():
            if k == "errores":
                for e in v[:25]:
                    log(f"   ✗ {e}")
            else:
                log(f"   {k:<45} {v}")
    return out
