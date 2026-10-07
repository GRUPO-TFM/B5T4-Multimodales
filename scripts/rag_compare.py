"""
Compara buscadores del agente 3 con el golden set (evals/preguntas_rag.yaml): BM25 · denso · híbrido.

Mide, para cada buscador, recall@1/3/8 (¿sale una de las fuentes esperadas entre los k primeros?) y la latencia
media de búsqueda. Con --answers, además pide la respuesta completa (LLM + Jev si hay clave) con el buscador
elegido y enseña la esperada al lado; la pregunta trampa (sin fuente) debe acabar en «No consta».

Uso:  uv run python scripts/rag_compare.py                     # solo buscadores (no gasta LLM)
      uv run python scripts/rag_compare.py --answers hybrid    # + respuestas con ese buscador
Guarda el resultado en out/rag/compare_<fecha>.json para la memoria del trabajo.
"""
import argparse
import json
import statistics
import time
from datetime import datetime

import yaml

from b5t4.agents.rag import search
from b5t4.config import ROOT, get_settings


def retrievers():
    from b5t4.agents.rag import dense
    from b5t4.agents.rag.hybrid import search_hybrid

    out = {"bm25": search}
    if dense.available():
        out["denso"] = dense.search_dense
        out["hybrid"] = search_hybrid
    else:
        print("(sin índice denso: solo BM25. Para el resto: uv run python scripts/rag_dense_index.py)\n")
    return out


def recall(fn, qs, k):
    hits = {1: 0, 3: 0, k: 0}
    times, rows = [], []
    for q in qs:
        t0 = time.perf_counter()
        ranked = [c.source for _, c in fn(q["pregunta"], k)]
        times.append(time.perf_counter() - t0)
        pos = next((i + 1 for i, s in enumerate(ranked) if s in set(q["fuentes"])), None)
        for kk in hits:
            hits[kk] += bool(pos and pos <= kk)
        rows.append({"id": q["id"], "pos": pos})
    return hits, statistics.mean(times), rows


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--answers", choices=["bm25", "denso", "hybrid"], help="pedir también las respuestas")
    a = p.parse_args()

    allq = yaml.safe_load((ROOT / "evals" / "preguntas_rag.yaml").read_text(encoding="utf-8"))
    qs = [q for q in allq if q.get("fuentes")]
    k = get_settings().top_k
    fns = retrievers()
    result = {"fecha": datetime.now().isoformat(timespec="seconds"), "k": k, "n": len(qs), "buscadores": {}}

    print(f"{'buscador':<8} {'r@1':>5} {'r@3':>5} {'r@' + str(k):>5}  latencia")
    per_q = {}
    for name, fn in fns.items():
        hits, lat, rows = recall(fn, qs, k)
        result["buscadores"][name] = {"recall": {str(kk): v for kk, v in hits.items()}, "latencia_s": round(lat, 3),
                                      "posiciones": rows}
        per_q[name] = {r["id"]: r["pos"] for r in rows}
        print(f"{name:<8} {hits[1]:>3}/{len(qs)} {hits[3]:>3}/{len(qs)} {hits[k]:>3}/{len(qs)}  {lat * 1000:6.0f} ms")

    print("\nposición de la fuente correcta por pregunta (— = no sale en el top-k)")
    print("id    " + "".join(f"{n:>8}" for n in fns))
    for q in qs:
        print(f"{q['id']:<6}" + "".join(f"{(per_q[n][q['id']] or '—'):>8}" for n in fns))

    if a.answers:
        from b5t4.agents.rag.verify import ask_verified

        fn = fns.get(a.answers, search)
        result["respuestas"] = []
        print(f"\nrespuestas con {a.answers}:")
        for q in allq:
            r = ask_verified(q["pregunta"], search_fn=fn, log=lambda *_: None)
            print(f"\n{q['id']} {q['pregunta']}\n  respuesta: {r.text}\n  esperada:  {q['respuesta']}")
            if r.verified:
                print(f"  jev: {len(r.sentences)} frases · {r.removed} quitadas · {r.flagged} a revisar")
            print(f"  tiempos: {r.answer.timings}")
            result["respuestas"].append({"id": q["id"], "respuesta": r.text, "esperada": q["respuesta"],
                                         "verificada": r.verified, "quitadas": r.removed, "a_revisar": r.flagged,
                                         "tiempos": r.answer.timings})

    out = get_settings().out_dir / "rag" / f"compare_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nguardado en {out}")
