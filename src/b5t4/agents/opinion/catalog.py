"""
Catálogo de activos de la Opinión Corporativa. Es lo que permite comparar dos ediciones sin errores.

El mismo activo se escribe distinto en cada PDF («Deuda soberana: (UST10)» frente a «(UST 10 años)»). Si cada
edición se extrajera con sus propios nombres, la comparación vería un activo que desaparece y otro que aparece.
Por eso el LLM no inventa el nombre: elige un identificador de esta lista, y la comparación cruza identificadores.
"""
from __future__ import annotations

# (identificador, región, nombre para el informe)
ASSETS: list[tuple[str, str, str]] = [
    ("us.equity", "EE.UU.", "Renta variable EE.UU. (S&P 500)"),
    ("us.govt10y", "EE.UU.", "Bono del Tesoro a 10 años (UST10)"),
    ("us.ig", "EE.UU.", "Crédito grado de inversión EE.UU. (CDX IG)"),
    ("us.hy", "EE.UU.", "Crédito high yield EE.UU. (CDX HY)"),
    ("us.fx", "EE.UU.", "Dólar (índice DXY)"),
    ("eu.equity", "Europa", "Renta variable europea (Stoxx Europe)"),
    ("eu.govt_core", "Europa", "Deuda soberana países centrales (Bund)"),
    ("eu.govt_periphery", "Europa", "Deuda soberana periferia (IT, ES, PT, IR, GR)"),
    ("eu.ig", "Europa", "Crédito grado de inversión europeo (iTraxx IG)"),
    ("eu.hy", "Europa", "Crédito high yield europeo (iTraxx HY)"),
    ("cn.equity_shanghai", "China", "Bolsa de Shanghái"),
    ("cn.equity_shenzhen", "China", "Bolsa de Shenzhen"),
    ("cn.equity_hangseng", "China", "Bolsa de Hong Kong (Hang Seng)"),
    ("cn.equity_star50", "China", "STAR 50"),
    ("cn.govt10y", "China", "Bono soberano chino a 10 años"),
    ("cn.fx", "China", "Yuan (CNY/USD)"),
    ("jp.equity", "Japón", "Renta variable japonesa (Topix)"),
    ("jp.govt", "Japón", "Deuda soberana japonesa"),
    ("jp.fx", "Japón", "Yen (USD/JPY)"),
    ("in.equity", "India", "Renta variable india (SENSEX)"),
    ("in.govt", "India", "Deuda soberana india"),
    ("in.corp", "India", "Deuda corporativa india"),
    ("in.fx", "India", "Rupia (INR/USD)"),
    ("il.equity", "Israel", "Renta variable israelí (TLV35)"),
    ("il.govt", "Israel", "Deuda soberana israelí a 10 años"),
    ("il.corp", "Israel", "Deuda corporativa israelí"),
    ("il.fx", "Israel", "Séquel (ILS/USD)"),
    ("br.equity", "Brasil", "Renta variable brasileña (Bovespa)"),
    ("br.debt_local", "Brasil", "Deuda brasileña en reales (BRL)"),
    ("br.debt_usd", "Brasil", "Deuda brasileña en dólares"),
    ("br.fx", "Brasil", "Real brasileño (BRL/USD)"),
    ("mx.equity", "México", "Renta variable mexicana (IPC)"),
    ("mx.debt_local", "México", "Deuda mexicana en pesos (MXN)"),
    ("mx.debt_usd", "México", "Deuda mexicana en dólares"),
    ("mx.fx", "México", "Peso mexicano (MXN/USD)"),
    ("ar.govt_usd", "Argentina", "Deuda soberana argentina a 10 años en USD"),
    ("ar.fx", "Argentina", "Peso argentino (USD/ARS)"),
    ("oil", "Materias primas", "Petróleo (WTI)"),
    ("gold", "Materias primas", "Oro"),
]
BY_ID = {a: (r, l) for a, r, l in ASSETS}
REGION_ORDER = list(dict.fromkeys(r for _, r, _ in ASSETS))


def catalog_text() -> str:
    """El catálogo tal y como se le da al LLM."""
    return "\n".join(f"{a} | {r} | {l}" for a, r, l in ASSETS)


def label_of(asset_id: str, fallback: str = "") -> str:
    return BY_ID.get(asset_id, ("", fallback or asset_id))[1]


def region_of(asset_id: str, fallback: str = "") -> str:
    return BY_ID.get(asset_id, (fallback or "Otros", ""))[0]


# ------------------------------------------------------------------ tabla sinóptica: nombres en español
GROUPS_ES = {
    "equity": "Renta variable", "fixed income core countries": "Deuda soberana · países centrales",
    "fixed income peripheral": "Deuda soberana · periferia europea", "fixed income credit": "Crédito",
    "fixed income emea": "Deuda soberana · EMEA", "fixed income asia": "Deuda soberana · Asia (moneda local)",
    "fixed income latam": "Deuda soberana · Latinoamérica", "commodities": "Materias primas", "fx": "Divisas",
}
_COUNTRIES = {"spain": "España", "italy": "Italia", "portugal": "Portugal", "ireland": "Irlanda", "greece": "Grecia",
              "china": "China", "india": "India", "singapore": "Singapur", "indonesia": "Indonesia",
              "south korea": "Corea del Sur", "taiwan": "Taiwán", "philippines": "Filipinas", "malaysia": "Malasia",
              "thailand": "Tailandia", "vietnam": "Vietnam", "turkey": "Turquía", "mexico": "México", "brazil": "Brasil"}
_FIXED = {"usa s p 500": "S&P 500 (EE.UU.)", "europe stoxx europe 600": "Stoxx Europe 600", "spain ibex 35": "IBEX 35",
          "mexico mxse ipc": "IPC (México)", "brazil bovespa": "Bovespa (Brasil)", "japan topix": "Topix (Japón)",
          "china sse comp a share": "Shanghái (SSE Composite)", "china shenzen composite": "Shenzhen Composite",
          "india sensex": "Sensex (India)", "vietnam vn index": "VN Index (Vietnam)", "msci em asia in usd": "MSCI EM Asia (USD)",
          "us treasury 10 year govie": "Bono EE.UU. 10 años", "uk 10 year gilt": "Gilt británico 10 años",
          "german 10 year bund": "Bund alemán 10 años", "japanese 10 year govie": "Bono japonés 10 años",
          "credit eur ig itraxx europe": "Crédito EUR IG (iTraxx Europe)", "credit eur hy itraxx xover": "Crédito EUR HY (iTraxx Crossover)",
          "credit usd ig cdx ig": "Crédito USD IG (CDX IG)", "credit usd hy cdx hy": "Crédito USD HY (CDX HY)",
          "oil wti": "Petróleo WTI ($/barril)", "gold": "Oro ($/onza)", "cny price of 1 usd": "USDCNY"}


def group_es(asset_class: str) -> str:
    """«Fixed Income Asia (Local curncy)» → «Deuda soberana · Asia (moneda local)»: se ignora lo que va entre paréntesis."""
    import re as _re
    k = _re.sub(r"[^a-z]+", " ", _re.sub(r"\(.*?\)", "", asset_class.lower())).strip()
    return GROUPS_ES.get(k, asset_class)


def row_label(index: str) -> str:
    """«Spain - 10yr Gov bond» → «España 10 años»; «USDJPY (price of 1 USD)» → «USDJPY»."""
    import re as _re
    import unicodedata as _u

    k = "".join(c for c in _u.normalize("NFKD", index.lower()) if not _u.combining(c))
    k = _re.sub(r"[^a-z0-9]+", " ", k).strip()
    if k in _FIXED:
        return _FIXED[k]
    if m := _re.match(r"^([a-z ]+?) 10yr gov(?:ie| bond)\s*(loc\w*|l|usd)?", k):
        country = _COUNTRIES.get(m.group(1).strip(), m.group(1).strip().title())
        suffix = {"usd": " (USD)"}.get(m.group(2) or "", " (local)" if (m.group(2) or "").startswith("loc") and country in ("México", "Brasil") else "")
        return f"{country} 10 años{suffix}"
    if m := _re.match(r"^([a-z]{6}) price of 1", k):
        return m.group(1).upper()
    return index


def fmt_es(x: float | None, unit: str = "", rate: bool = False) -> str:
    """Formato español: 19584 → «19.584»; 4.25 → «4,25»; rendimientos siempre con dos decimales (10 → «10,00»)."""
    if x is None:
        return "—"
    if rate:
        s = f"{x:.2f}".replace(".", ",")
    elif abs(x) >= 1000:
        s = f"{x:,.0f}".replace(",", ".")
    elif x == int(x) and abs(x) >= 10:
        s = f"{x:.0f}"
    else:
        s = f"{x:.2f}".rstrip("0").rstrip(".") if abs(x) >= 100 else f"{x:.2f}"
        s = s.replace(".", ",")
    return s + (f" {unit}" if unit else "")


def fmt_delta(d: float | None, unit: str | None) -> str:
    if d is None:
        return ""
    v = f"{d:+.1f}".replace(".", ",") if unit == "%" else f"{d:+.0f}"
    return f"{v} {unit or ''}".strip()


# ------------------------------------------------------------------ cruce recomendaciones ↔ tabla sinóptica
# El mismo objetivo aparece dos veces en el PDF (en el texto del país y en la tabla): se comprueba que coinciden.
# asset_id → (clave de fila de la tabla, tipo: «rate» = rendimiento %, «spread» = pb, «level» = precio/tipo de cambio)
TABLE_MAP = {
    "us.govt10y": ("us treasury 10 year govie", "rate"), "eu.govt_core": ("german 10 year bund", "rate"),
    "cn.govt10y": ("china 10yr gov bond", "rate"), "jp.govt": ("japanese 10 year govie", "rate"),
    "us.ig": ("credit usd ig cdx ig", "spread"), "us.hy": ("credit usd hy cdx hy", "spread"),
    "eu.ig": ("credit eur ig itraxx europe", "spread"), "eu.hy": ("credit eur hy itraxx xover", "spread"),
    "jp.fx": ("usdjpy price of 1 usd", "level"), "cn.fx": ("cny price of 1 usd", "level"),
    "br.fx": ("usdbrl price of 1 usd", "level"), "mx.fx": ("usdmxn price of 1 usd", "level"),
    "ar.fx": ("usdars price of 1 usd", "level"), "oil": ("oil wti", "level"), "gold": ("gold", "level"),
}
