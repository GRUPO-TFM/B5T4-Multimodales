"""
Paso 2 · De cada PDF a datos estructurados. Es el único paso de este agente en el que un LLM LEE.

Diseño para que sea fiable y barato a la vez:
  1. Sin LLM se decide QUÉ leer: la plantilla de la casa pone títulos fijos («Perspectivas de mercado: recomendaciones
     y objetivos», «Tendencias estructurales», «Tabla sinóptica…»), y cada página de coyuntura es de UN país.
  2. Una llamada pequeña por página de recomendaciones (en paralelo), con la región ya detectada y el catálogo
     reducido a esa región. Un prompt corto con una sola región falla mucho menos que uno largo con ocho, y el
     error de una página no contamina a las demás.
  3. La tabla sinóptica es una IMAGEN: se recorta en dos mitades a buena resolución y las lee el modelo de visión.
     Luego Python comprueba cada fila: en índices, divisas y materias primas, rentabilidad esperada ≈ objetivo/precio − 1
     (la propia tabla trae su «suma de control»).
  4. Para cada recomendación extraída, Python busca en el texto de la página la LÍNEA LITERAL que la respalda
     (evidencia). Si no la encuentra, la fila queda marcada «revisar». El informe enseña esa línea.
  5. Todo se guarda en index/opinion/<pdf>_<md5>.json: un PDF se paga una vez.
"""
from __future__ import annotations

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from ...config import get_settings
from ...corpus.extract import pdf_pages
from .catalog import ASSETS, catalog_text, label_of, region_of
from .llmcall import Usage, ask_json, load_config
from .schemas import Edition, EditionData, Risk, TargetRow, Trend, View

REGION_KEYS = {
    "EE.UU.": ["ee.uu", "s&p", "ust", "cdx"], "Europa": ["europa", "stoxx", "itraxx", "bund"],
    "China": ["shangh", "shenzh", "star 50", "cny"], "Japón": ["japon", "topix", "jpy"],
    "Israel": ["israel", "tlv", "ils"], "India": ["india", "sensex", "inr"], "Brasil": ["brasil", "bovespa", "brl"],
    "México": ["mexico", "mxn", "ipc"], "Argentina": ["argentina", "ars"],
}


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


# ------------------------------------------------------------------ qué páginas leer (sin LLM)
def route_pages(pages: dict[int, str]) -> dict[str, list[int]]:
    up = {n: t.upper() for n, t in pages.items()}
    return {
        "views": [n for n, t in up.items() if "PERSPECTIVAS DE MERCADO" in t],
        "trends": [n for n, t in up.items() if "TENDENCIAS ESTRUCTURALES" in t and len(t) > 1000],
        "commodities": [n for n, t in up.items() if ("MATERIAS PRIMAS" in t or "METALES PRECIOSOS" in t) and len(t) > 1000],
        "synoptic": [n for n, t in up.items() if "TABLA SIN" in t and len(t) < 1500][:1],
    }


def detect_region(page_text: str) -> str | None:
    """La región de una página de coyuntura, por las palabras clave de su bloque de recomendaciones y su cabecera."""
    i = _norm(page_text).find("perspectivas de mercado")
    block = _norm(page_text)[i:i + 1200] if i >= 0 else ""
    head = _norm(page_text)[:400]
    best, score = None, 0
    for region, keys in REGION_KEYS.items():
        # límite de palabra: «ust» no debe contar dentro de «ajuste» o «robusto», ni «ils»/«inr»/«ars» dentro de otras palabras
        pats = [re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])") for k in keys]
        sc = sum(3 * len(pat.findall(block)) + len(pat.findall(head)) for pat in pats)
        if sc > score:
            best, score = region, sc
    return best


def _block(page_text: str) -> str:
    """Solo el bloque de recomendaciones (lo que sigue al título), no toda la página: prompt corto y sin ruido."""
    i = _norm(page_text).find("perspectivas de mercado")
    return page_text[i:] if i >= 0 else page_text


# ------------------------------------------------------------------ esquemas de respuesta del LLM
class _Views(BaseModel):
    views: list[View]


class _TrendsAndCommodities(BaseModel):
    trends: list[Trend] = Field(default_factory=list)
    gold_risks: list[Risk] = Field(default_factory=list)
    commodities: list[View] = Field(default_factory=list, description="petróleo (oil) y oro (gold): postura u objetivo")


class _Table(BaseModel):
    rows: list[TargetRow]


SYS_VIEWS = """Extraes las recomendaciones del bloque «Perspectivas de mercado: recomendaciones y objetivos» de la
Opinión Corporativa de Andbank (texto de UNA página, UNA región). Una fila por activo.

Reglas:
- asset_id: elige SIEMPRE del catálogo que te doy (columna 1). Si un activo no está, «otro:<descripcion-corta>».
- Si una línea agrupa dos activos («Shanghái / Shenzhén: INFRAPONDERAR / NEUTRAL»), una fila por activo, en orden.
- stance: SOBREPONDERAR, NEUTRAL-SOBREPONDERAR, NEUTRAL, NEUTRAL-INFRAPONDERAR, INFRAPONDERAR, FAVORABLE
  (p. ej. «FAVORABLE AL JPY») o NEGATIVO. stance_raw: el texto literal de la postura, tal cual (si viene
  abreviado, «SOBREPOND.», cópialo abreviado).
- asset_class de la tabla y nombres: no añadas aclaraciones entre paréntesis que no estén en el texto.
- target_raw: el objetivo literal completo entre paréntesis (rendimiento, diferencial, nivel, tipo de cambio).
  target_value: el número principal (5,00% → 5.0; 1.600 → 1600; «900 pb; 13,50%» → null porque hay dos).
  Si hay varios objetivos de varios países en la misma línea (periferia), target_value = null.
- A veces el texto viene en columnas y la etiqueta del activo aparece separada de su postura («Renta variable»
  en una línea y «: NEUTRAL» más abajo). Empareja por el orden del bloque; si no estás seguro, omite la fila.
- No incluyas nada que no sea una recomendación de este bloque."""

SYS_TRENDS = f"""Extraes datos de la Opinión Corporativa de Andbank (texto de varias páginas, cada una marcada [página N]).
1) trends: cada tema del bloque «Tendencias estructurales», con su conclusión (la palabra tras «Conclusión —»,
   p. ej. POSITIVA, NEUTRAL, FAVORABLE) y una frase fiel que la resuma. Título breve del tema.
2) gold_risks: los riesgos para el oro con su calificación literal (BAJO, MEDIO, MEDIO-ALTO…).
3) commodities: postura u objetivo del petróleo (asset_id «oil») y del oro (asset_id «gold») si el texto los da;
   stance = OTRA si solo hay objetivo de precio; target_value = precio objetivo.
Cita la página ([página N]). No inventes: si algo no aparece, deja la lista vacía.
Catálogo para commodities:
{catalog_text()}"""

SYS_TABLE = """Lees la «Tabla sinóptica de rentabilidades esperadas» de Andbank, partida en dos imágenes
(mitad superior y mitad inferior; la fila del corte puede aparecer en las dos: no la repitas).
Devuelve TODAS las filas, de arriba abajo:
- asset_class: la columna «Asset Class» vigente para la fila (Equity, Fixed Income Core countries, …, Fx).
- index: el texto literal de la columna «Indices».
- current: «Current Price»; target: «Andbank's Target Price Year End»; expected_perf: «Expected Performance» en %
  con signo (-0,6% → -0.6). Punto decimal: 19.584 (miles) → 19584; 4,25 → 4.25.
Si una celda no se lee con seguridad, null antes que adivinar."""


# ------------------------------------------------------------------ comprobaciones sin LLM
def _flat(text: str) -> str:
    """El PDF parte las líneas de LatAm en trozos («: SOBREPOND⏎. (dif⏎. obj.: 900 pb»): se aplana todo en una línea."""
    t = re.sub(r"\s+", " ", text)
    t = re.sub(r"\s+([.,;:%)])", r"\1", t)
    return re.sub(r"\s*-\s*", "-", t) if False else t


def find_evidence(page_text: str, v: View) -> str | None:
    """El fragmento literal del PDF que contiene la postura (y los números del objetivo, si lo hay) de esta fila.
    Lo busca Python, no el LLM: si no aparece, la fila queda marcada como «revisar»."""
    flat = re.sub(r"\s*-\s*", "-", _flat(_block(page_text)))       # «NEUTRAL - SOBREPONDERAR» → «NEUTRAL-SOBREPONDERAR»
    n = _norm(flat)
    if len(n) != len(flat):                                           # (raro) ligaduras: se pierde la versión con tildes
        flat = n
    stance_key = re.sub(r"\s*-\s*", "-", _norm(v.stance_raw).strip())[:9]   # «SOBREPOND.» abrevia SOBREPONDERAR
    digits = lambda t: re.sub(r"[^0-9]", "", t)
    nums = [digits(x) for x in re.findall(r"\d+(?:[.,]\d+)?", v.target_raw or "")][:2]
    keys = [k for k in re.findall(r"[a-z&0-9]{3,}", _norm(v.label))
            if k not in ("renta", "variable", "deuda", "soberana", "tipo", "cambio", "indice", "bono", "anos", "credito",
                         "grado", "inversion", "del", "bolsa", "europea", "europeo", "chino", "japonesa", "brasilena", "mexicana")]
    starts_re = re.compile(r"renta variable|deuda |tipo de cambio|-centrales|-p\. centrales|-perif|shangh|star 50|divisa")
    best, best_score = None, -1
    for m in re.finditer(re.escape(stance_key), n):
        pos = m.start()
        # el tramo del activo: desde el último arranque de activo antes de la postura hasta el cierre de su paréntesis
        a = max([x.start() for x in starts_re.finditer(n, max(0, pos - 110), pos)] or [max(0, pos - 60)])
        tail = n[m.end():m.end() + 160]
        m_end = re.search(r"\)|(?= renta variable| deuda | tipo de cambio| -)", tail)
        b = m.end() + (m_end.end() if m_end else 40)
        if nums and not all(x in digits(n[m.end():b]) for x in nums):
            continue
        score = sum(k in n[a:m.end()] for k in keys)
        if score > best_score:
            best, best_score = (a, b), score
    if best is None:
        return None
    a, b = best
    if a > 0 and flat[a - 1] not in " ([":                                   # no cortar una palabra por la mitad
        a = flat.rfind(" ", 0, a) + 1
    return re.sub(r"\s+", " ", flat[a:b]).strip()[:230]


def check_table_row(r: TargetRow) -> TargetRow:
    """Índices, divisas y materias primas: la rentabilidad esperada debe ser objetivo/precio − 1 (±0,4 pp)."""
    cls = _norm(r.asset_class)
    if r.current and r.target and r.expected_perf is not None and not cls.startswith("fixed"):   # renta fija: rentabilidad a 12 meses, no comprobable
        calc = (r.target / r.current - 1) * 100
        # La tabla imprime precio y objetivo con dos decimales (0,81 → 0,77) pero calcula la rentabilidad con los
        # valores sin redondear: en divisas ese redondeo vale hasta ±1,5 pp. La tolerancia lo absorbe; un dígito mal
        # leído se sigue detectando porque desvía varios puntos.
        tol = 0.4 + (100 * (0.005 / abs(r.current) + 0.005 / abs(r.target)) if abs(r.current) < 100 else 0)
        r.consistent = abs(calc - r.expected_perf) <= tol
    return r


# ------------------------------------------------------------------ extracción
def _cache_path(ed: Edition) -> Path:
    return get_settings().index_dir / "opinion" / f"{ed.path.stem}{'_' + ed.md5[:8] if ed.md5 else ''}.json"


BANDS = {2: ((0.10, 0.56), (0.54, 0.98)), 3: ((0.10, 0.42), (0.40, 0.71), (0.69, 0.98))}


def _table_crops(ed: Edition, page: int, out_dir: Path, parts: int = 2) -> tuple[list[Path], Path]:
    """Recortes PNG de la tabla para el modelo de visión (2 o 3 bandas con solape) y la página entera en JPEG
    (para enseñarla en el informe: ~150 kB en vez de ~900 kB en PNG)."""
    import pypdfium2 as pdfium

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(ed.path))
    try:
        im = pdf[page - 1].render(scale=2.4).to_pil()
    finally:
        pdf.close()
    w, h = im.size
    full = out_dir / f"{ed.path.stem}_p{page:02d}.jpg"
    if not full.exists():
        small = im.convert("RGB")
        small.thumbnail((1200, 4000))
        small.save(full, quality=72, optimize=True)
    crops = []
    for k, (a, b) in enumerate(BANDS[parts]):
        p = out_dir / f"{ed.path.stem}_p{page:02d}_{parts}_{k}.png"
        im.crop((0, int(h * a), w, int(h * b))).save(p)
        crops.append(p)
    return crops, full


def extract_edition(ed: Edition, use_cache: bool = True, log=print) -> EditionData:
    cache = _cache_path(ed)
    if use_cache and cache.exists():
        data = EditionData.model_validate_json(cache.read_text(encoding="utf-8"))
        log(f"  {ed.label}: extracción guardada ({cache.name}; costó {data.usage.get('coste_usd', 0)} $ cuando se leyó)")
        data.usage = {**data.usage, "cached": True}
        return _recheck(data, ed)

    cfg, usage = load_config(), Usage(load_config())
    s = get_settings()
    pages = {p.page: p.text for p in pdf_pages(ed.path)}
    route = route_pages(pages)
    log(f"  {ed.label}: páginas → recomendaciones {route['views']} · tendencias {route['trends']} · "
        f"materias primas {route['commodities']} · tabla sinóptica {route['synoptic']}")

    def views_of(n: int) -> list[View]:
        region = detect_region(pages[n])
        ids = [a for a, r, l in ASSETS if r == region] if region else [a for a, _, _ in ASSETS]
        cat = "\n".join(f"{a} | {region_of(a)} | {label_of(a)}" for a in ids)
        user = f"Región de la página: {region or 'desconocida'}. Página {n}.\n\nCatálogo (id | región | nombre):\n{cat}\n\nTEXTO:\n{_block(pages[n])}"
        out = []
        for v in ask_json(_Views, SYS_VIEWS, user, cfg.model_text, cfg.reasoning, usage, log=log).views:
            v.page = n
            if region and not v.asset_id.startswith("otro:") and region_of(v.asset_id) != region:
                v.asset_id = f"otro:{_norm(v.label)[:30]}"      # un id de otra región aquí es un error del modelo
            out.append(v)
        return out

    def trends():
        nums = route["trends"] + route["commodities"]
        if not nums:
            return _TrendsAndCommodities()
        txt = "\n\n".join(f"[página {n}]\n{pages[n]}" for n in nums)
        return ask_json(_TrendsAndCommodities, SYS_TRENDS, txt, cfg.model_text, cfg.reasoning, usage, log=log)

    def table():
        if not route["synoptic"]:
            log(f"  {ed.label}: no encuentro la tabla sinóptica")
            return [], None
        page = route["synoptic"][0]
        crops, full = _table_crops(ed, page, s.index_dir / "opinion" / "paginas")
        rows = ask_json(_Table, SYS_TABLE, f"Tabla sinóptica de la edición {ed.label} (página {page}).", cfg.model_vision,
                        cfg.reasoning, usage, images=crops, log=log).rows
        if len(rows) < 40:                                   # una tabla a medias no sirve: segundo intento con OTROS recortes
            log(f"  {ed.label}: la tabla solo trae {len(rows)} filas; reintento con tres bandas")   # (a temperatura 0, repetir
            crops, _ = _table_crops(ed, page, s.index_dir / "opinion" / "paginas", parts=3)        #  la misma imagen da lo mismo)
            rows = ask_json(_Table, SYS_TABLE.replace("en dos imágenes\n(mitad superior y mitad inferior", "en tres imágenes\n(bandas superior, central e inferior"),
                            f"Tabla sinóptica de la edición {ed.label} (página {page}). Devuelve las ~55 filas.",
                            cfg.model_vision, cfg.reasoning, usage, images=crops, log=log).rows
        seen, uniq = set(), []
        for r in rows:
            k = _norm(r.index)
            if k not in seen:
                seen.add(k); uniq.append(check_table_row(r))
        return uniq, str(full)

    with ThreadPoolExecutor(max_workers=8) as ex:
        f_views = [ex.submit(views_of, n) for n in route["views"]]
        f_t, f_tab = ex.submit(trends), ex.submit(table)
        views = [v for f in f_views for v in f.result()]
        tc = f_t.result()
        rows, full_img = f_tab.result()

    all_views = _clean_views(views + list(tc.commodities))
    for v in all_views:
        v.evidence = find_evidence(pages.get(v.page, ""), v)
    _attach_conclusions(pages, tc.trends)
    used = sorted(set(route["views"] + route["trends"] + route["commodities"] + route["synoptic"]))
    data = EditionData(edition=ed, views=all_views, targets=rows, trends=tc.trends, gold_risks=tc.gold_risks,
                       pages={n: pages[n] for n in used}, table_page=route["synoptic"][0] if route["synoptic"] else None,
                       table_image=full_img, usage=usage.summary())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(data.model_dump_json(indent=1), encoding="utf-8")
    bad = sum(v.evidence is None for v in all_views if not v.asset_id in ("oil", "gold"))
    inconsistent = sum(r.consistent is False for r in rows)
    log(f"  {ed.label}: {len(all_views)} recomendaciones ({bad} sin evidencia literal) · {len(rows)} filas de la tabla "
        f"({inconsistent} con suma de control fallida) · {len(tc.trends)} tendencias · {len(tc.gold_risks)} riesgos del oro "
        f"· {usage.summary()['tokens_entrada']}+{usage.summary()['tokens_salida']} tokens ≈ {usage.summary()['coste_usd']} $")
    return data


def _recheck(data: EditionData, ed: Edition | None = None) -> EditionData:
    """Lo que calcula Python (evidencia literal, suma de control, conclusiones, textos literales normalizados) se
    rehace SIEMPRE al cargar de la caché: la caché guarda la lectura del LLM, que es lo que cuesta dinero; las
    comprobaciones son gratis y así una mejora en el código llega a las ediciones ya leídas (sin esto, una
    tolerancia corregida seguía mostrando avisos antiguos en el informe)."""
    if ed is not None:
        data.edition = ed                                    # la ruta del PDF es la de ESTA máquina, no la de quien lo leyó
    data.views = _clean_views(data.views)
    for v in data.views:
        v.evidence = find_evidence(data.pages.get(v.page, ""), v)
    data.targets = [check_table_row(r) for r in data.targets]
    _attach_conclusions(data.pages, data.trends)
    if data.table_image and data.table_page and (not Path(data.table_image).exists() or Path(data.table_image).suffix == ".png"):
        _, full = _table_crops(data.edition, data.table_page, get_settings().index_dir / "opinion" / "paginas")
        data.table_image = str(full)
    return data


def _conclusions(page_text: str) -> list[str]:
    """«Conclusión — POSITIVA. …» (3T) u «Opinión — FAVORABLE. …» (4T), en el orden de la página."""
    flat = _flat(page_text)
    return [f"{m.group(1)} — {m.group(2).strip()}"[:260]
            for m in re.finditer(r"(Conclusi[oó]n|Opini[oó]n)\s*[—–-]\s*([^.]{0,60}\.[^.]{0,200})", flat)]


def _attach_conclusions(pages: dict[int, str], trends: list[Trend]) -> None:
    """Cada tema recibe la frase literal de su conclusión: por orden dentro de la página y, si no cuadra, por la palabra."""
    by_page: dict[int, list[Trend]] = {}
    for t in trends:
        by_page.setdefault(t.page, []).append(t)
    for n, ts in by_page.items():
        cs = _conclusions(pages.get(n, ""))
        if len(cs) == len(ts):
            for t, c in zip(ts, cs):
                t.evidence = c
            continue
        for t in ts:
            t.evidence = next((c for c in cs if _norm(t.conclusion).split()[0] in _norm(c)), None)


def _clean_views(views: list[View]) -> list[View]:
    """Nombres y regiones salen del catálogo, no del LLM; un mismo activo repetido se queda una sola vez."""
    out, seen = [], set()
    for v in views:
        if v.asset_id in seen:
            continue
        seen.add(v.asset_id)
        if not v.asset_id.startswith("otro:"):
            v.label, v.region = label_of(v.asset_id, v.label), region_of(v.asset_id, v.region)
        v.stance_raw = re.sub(r"\s*-\s*", "-", _flat(v.stance_raw).strip())           # «NEUTRAL - SOBREPOND.» → «NEUTRAL-SOBREPOND.»
        if v.target_raw:
            v.target_raw = _flat(v.target_raw).strip()                                # «dif . obj.: 500 bps ;» → «dif. obj.: 500 bps;»
        out.append(v)
    return out


def load_reference(ed: Edition) -> EditionData | None:
    """Extracción de referencia (evals/opinion_referencia.json), hecha a mano: para probar el agente sin claves y
    para medir la extracción con LLM. Devuelve None si esa edición no está en la referencia."""
    from ...config import ROOT

    ref_file = ROOT / "evals" / "opinion_referencia.json"
    if not ref_file.exists():
        return None
    ref = json.loads(ref_file.read_text(encoding="utf-8"))["ediciones"]
    d = next((v for v in ref.values() if v["fichero"] == ed.path.name), None)
    if d is None:
        return None
    pages = {p.page: p.text for p in pdf_pages(ed.path)}
    route = route_pages(pages)
    views = [View(**v) for v in d["views"]]
    for v in views:
        v.evidence = find_evidence(pages.get(v.page, ""), v)
    trends = [Trend(**t) for t in d["trends"]]
    _attach_conclusions(pages, trends)
    img = None
    if route["synoptic"]:
        _, full = _table_crops(ed, route["synoptic"][0], get_settings().index_dir / "opinion" / "paginas")
        img = str(full)
    return EditionData(edition=ed, views=views, targets=[TargetRow(**t) for t in d["targets"]], trends=trends,
                       gold_risks=[Risk(**r) for r in d["gold_risks"]], pages=pages,
                       table_page=route["synoptic"][0] if route["synoptic"] else None, table_image=img)
