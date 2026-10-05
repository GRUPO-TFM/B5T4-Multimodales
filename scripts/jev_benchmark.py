"""
Prueba de Jev (TypeSafe AI) para el pipeline B5-T4.

Tres experimentos con etiquetas a mano, en español e inglés:
  A. Filtrado de posts     — ¿habla de los resultados de Micron?  (Noul) + tipo de contenido (Choice)
  B. Verificador           — ¿el pasaje respalda la afirmación?    (Noul)   <- el uso más valioso
  C. Cumplimiento          — ¿la frase es una recomendación de inversión? (Noul)

Mide acierto, Brier (calibración), latencia y tokens. Guarda jev_resultados.json.

Uso:  uv run python scripts/jev_benchmark.py   (banco de pruebas que justificó usar Jev: docs/DECISIONES.md, n.º 6)
Lee la clave de JEV_API_KEY (o TYPESAFE_API_KEY). Endpoint y formato según docs.typesafe.ai (2-oct-2026).
"""
import json, os, statistics, sys, time
import requests

API = "https://api.typesafe.ai/v1/systemone"
KEY = os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
if not KEY:
    sys.exit("Falta JEV_API_KEY / TYPESAFE_API_KEY en el entorno")
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def ask(state: str, questions: dict, model: str = "jev-latest") -> tuple[dict, float, dict]:
    """Una llamada a Jev. Devuelve (answers, latencia_s, usage)."""
    t0 = time.perf_counter()
    r = requests.post(API, headers=HEADERS, json={"state": state, "model": model, "questions": questions}, timeout=30)
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    data = r.json()
    answers = data.get("answers", data)
    return answers, dt, data.get("usage", {})


def noul(instructions):            return {"type": "noul", "instructions": instructions}
def choice(instructions, crit):    return {"type": "choice", "instructions": instructions, "criteria": crit}


# ----------------------------------------------------------------------------- A. filtrado
POSTS = [  # (texto, relevante_para_resultados_micron, tipo)
    ("Micron just printed $54.2B revenue vs $51.3B consensus. HBM sold out through 2027. Guide 61.5B. Insane.", True, "hecho"),
    ("MU to the moon 🚀🚀🚀 1500 EOY easy", True, "opinion"),
    ("Micron guía 61.500 millones para el 1T FY27, un 8 % por encima del consenso. El margen bruto toca suelo este trimestre según la dirección.", True, "hecho"),
    ("Anyone else think the memory cycle peaks in 2027? Micron capex of $25B in H1 alone scares me.", True, "opinion"),
    ("Get rich with crypto signals, DM me for the private group!!!", False, "spam"),
    ("Samsung y SK Hynix también suben hoy tras los resultados de Micron: el sector memoria entero se mueve.", True, "hecho"),
    ("Just made a sandwich. Great day.", False, "otro"),
    ("Nvidia Blackwell demand commentary from Jensen at GTC was bullish for the whole AI chain.", False, "opinion"),
    ("El PER de Micron a 12 meses vista es 6,6x. El mercado descuenta el final del ciclo.", True, "hecho"),
    ("Micron 2021 earnings were also a beat and the stock fell 40% after. History rhymes.", True, "opinion"),
    ("Apple presenta el nuevo iPhone con más memoria RAM.", False, "hecho"),
    ("lol imagine not owning MU rn 💀", True, "meme"),
]
TIPOS = {"hecho": "afirmación verificable con cifras o datos", "opinion": "opinión o predicción personal",
         "meme": "broma o reacción sin contenido informativo", "spam": "publicidad o estafa", "otro": "no relacionado con mercados"}

# ----------------------------------------------------------------------------- B. verificador (datos reales del 30-sep-2026)
PASAJE_NOTA = ("Micron reported fiscal Q4 2026 revenue of $54.23 billion and non-GAAP diluted EPS of $33.42. "
               "Non-GAAP gross margin was 87.0%. For fiscal Q1 2027 the company guided revenue of $61.5 billion ± $1.5 billion, "
               "non-GAAP gross margin of approximately 86.25% and non-GAAP EPS of $38.15 ± $1.00. Capital expenditures were $10.77 billion in the quarter and $27.37 billion for fiscal 2026.")
PASAJE_CALL = ("Management said the vast majority of calendar 2027 HBM bit supply is sold out at significantly higher prices than in 2026. "
               "DRAM and NAND price increases are expected to continue at a more moderate pace through fiscal 2027. "
               "Fiscal Q1 should represent the gross-margin floor for the year. The industry should remain supply constrained through calendar 2028. "
               "First-half fiscal 2027 capex is projected at approximately $25 billion, with higher spending in the second half.")
CLAIMS = [  # (afirmación, pasaje, respaldada)
    ("Los ingresos del 4T FY26 fueron 54.200 millones de dólares.", PASAJE_NOTA, True),
    ("El BPA no GAAP del trimestre fue de 33,42 dólares.", PASAJE_NOTA, True),
    ("Micron guía un margen bruto del 87 % para el 1T FY27.", PASAJE_NOTA, False),   # guía 86,25; 87 fue el 4T
    ("La guía de ingresos para el 1T FY27 es de 61.500 millones.", PASAJE_NOTA, True),
    ("El capex de todo el año fiscal 2027 será de 25.000 millones.", PASAJE_CALL, False),  # es el 1S
    ("La mayor parte del suministro de HBM de 2027 ya está vendido a precios más altos.", PASAJE_CALL, True),
    ("La dirección espera que los precios de DRAM bajen en 2027.", PASAJE_CALL, False),
    ("La oferta del sector seguirá tensionada hasta 2028.", PASAJE_CALL, True),
    ("El margen bruto del 1T FY27 será el mínimo del año.", PASAJE_CALL, True),
    ("Micron recompró acciones por 5.000 millones en el trimestre.", PASAJE_NOTA, False),  # no está en el pasaje
    ("The company guided Q1 EPS of $38.15 plus or minus one dollar.", PASAJE_NOTA, True),
    ("Capex in fiscal 2026 was below $20 billion.", PASAJE_NOTA, False),
]

# ----------------------------------------------------------------------------- C. cumplimiento
FRASES = [  # (frase, es_recomendación_de_inversión)
    ("Con un PER de 6,6 veces, el mercado ya descuenta el ciclo.", False),
    ("Es el momento de comprar Micron antes de que suba más.", True),
    ("Recomendamos incorporar MU a cartera con un objetivo de 1.500 dólares.", True),
    ("La dirección espera otro año récord con crecimiento secuencial cada trimestre.", False),
    ("Si tienes liquidez, no esperes: esta acción va a doblar.", True),
    ("Esto es información, no una recomendación de inversión.", False),
    ("Los analistas de consenso tienen un precio objetivo medio de 1.469 dólares.", False),
    ("Vende ahora y recoge beneficios, el ciclo de memoria siempre acaba igual.", True),
    ("Memory stocks are a guaranteed win this year.", True),
    ("HBM supply for 2027 is largely sold out, according to management.", False),
]


def brier(pairs):  # pairs de (prob, etiqueta bool)
    return statistics.mean((p - float(y)) ** 2 for p, y in pairs)


def main():
    out = {"A": [], "B": [], "C": []}
    lat, toks = [], 0

    print("\n=== A. Filtrado de posts ===")
    hits = 0; pairs = []
    for i, (txt, rel, tipo) in enumerate(POSTS):
        # v2: dos preguntas atómicas en vez de una compuesta (la v1 preguntaba por "resultados del 30-sep"
        # y el modelo respondía literalmente: los memes y opiniones sobre MU quedaban en 0,2-0,4)
        ans, dt, usage = ask(txt, {
            "micron": noul("El post menciona a Micron Technology o a su acción (ticker MU)."),
            "mercado": noul("El post habla de la situación financiera, los resultados, las perspectivas o la cotización de una empresa de semiconductores o memoria."),
            "tipo": choice("¿Qué tipo de contenido es este post?", TIPOS),
        })
        if i == 0: print("respuesta cruda:", json.dumps(ans, ensure_ascii=False)[:500])
        p = min(ans["micron"]["noul"], ans["mercado"]["noul"]); t = ans["tipo"]["choice"]
        ok = (p >= 0.5) == rel; hits += ok; pairs.append((p, rel)); lat.append(dt); toks += usage.get("input_tokens", 0)
        out["A"].append({"post": txt, "p_relevante": p, "p_micron": ans["micron"]["noul"], "p_mercado": ans["mercado"]["noul"], "esperado": rel, "tipo": t, "tipo_esperado": tipo, "ok": ok, "ms": round(dt * 1000)})
        print(f"{'✓' if ok else '✗'} p={p:.2f} tipo={t:<8} ({tipo:<8}) {dt*1000:5.0f} ms  {txt[:60]}")
    print(f"acierto relevancia {hits}/{len(POSTS)} · Brier {brier(pairs):.3f}")

    print("\n=== B. Verificador: ¿el pasaje respalda la afirmación? ===")
    hits = 0; pairs = []
    for claim, pasaje, y in CLAIMS:
        state = f"PASAJE FUENTE:\n{pasaje}\n\nAFIRMACIÓN:\n{claim}"
        ans, dt, usage = ask(state, {"respaldada": noul("La AFIRMACIÓN está respaldada por el PASAJE FUENTE: se refiere al mismo periodo y al mismo concepto, y las cifras coinciden admitiendo redondeo razonable (54.200 millones y $54.23 billion son la misma cifra). Si el pasaje no lo menciona, o el periodo o el concepto difieren, NO está respaldada.")})
        p = ans["respaldada"]["noul"]; ok = (p >= 0.5) == y; hits += ok; pairs.append((p, y)); lat.append(dt); toks += usage.get("input_tokens", 0)
        out["B"].append({"afirmacion": claim, "p_respaldada": p, "esperado": y, "ok": ok, "ms": round(dt * 1000)})
        print(f"{'✓' if ok else '✗'} p={p:.2f} esperado={y!s:<5} {dt*1000:5.0f} ms  {claim[:70]}")
    print(f"acierto {hits}/{len(CLAIMS)} · Brier {brier(pairs):.3f}")

    print("\n=== C. Cumplimiento: ¿es recomendación de inversión? ===")
    hits = 0; pairs = []
    for frase, y in FRASES:
        ans, dt, usage = ask(frase, {"recomendacion": noul("Esta frase constituye una recomendación de inversión personalizada o una incitación a comprar o vender un valor (en el sentido de MiFID II), y no mera información o descripción de hechos.")})
        p = ans["recomendacion"]["noul"]; ok = (p >= 0.5) == y; hits += ok; pairs.append((p, y)); lat.append(dt); toks += usage.get("input_tokens", 0)
        out["C"].append({"frase": frase, "p_recomendacion": p, "esperado": y, "ok": ok, "ms": round(dt * 1000)})
        print(f"{'✓' if ok else '✗'} p={p:.2f} esperado={y!s:<5} {dt*1000:5.0f} ms  {frase[:70]}")
    print(f"acierto {hits}/{len(FRASES)} · Brier {brier(pairs):.3f}")

    print(f"\nlatencia media {statistics.mean(lat)*1000:.0f} ms · mediana {statistics.median(lat)*1000:.0f} ms · tokens de entrada {toks} · coste ≈ {toks/1e6*0.042*100:.3f} céntimos")
    json.dump(out, open("jev_resultados_v2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("guardado jev_resultados_v2.json")


if __name__ == "__main__":
    main()
