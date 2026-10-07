"""
Paso 6 · Vídeo resumen (≤ 2 min): qué cambia y por qué, con voz de Gemini TTS (Kokoro de respaldo) y el motor de
fotogramas del repo.

El guion no lo escribe un modelo: se monta desde cambios.json con las frases YA verificadas (explicación y «porqué»
con cita literal). El vídeo no puede decir nada que no esté en el informe. Escenas:
  1. portada                      3. objetivos revisados (barras, pb)       5. cierre con cifras y aviso
  2. un cambio de recomendación   4. temas que entran y salen
     por escena, con sus razones
Presupuesto: video.max_seconds (120 s) a video.words_per_second (2,8 medido con Kokoro); si el guion se pasa,
se recortan razones y después la escena del oro, nunca un cambio de recomendación.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ...config import get_settings
from .catalog import fmt_delta

TEMPLATE = Path(__file__).resolve().parent / "templates" / "video.html"
MAX_POINT_WORDS = 26 # un argumento más largo no se lee en voz: no se trunca, se elige otro
DISCLAIMER = ("Resumen informativo de la Opinión Corporativa de Andbank. No es una recomendación personalizada ni una "
              "oferta de compra o venta. Rentabilidades esperadas no garantizadas.")


class Scene(BaseModel):
    id: str
    kind: str
    narration: str
    min_seconds: float = 3.0
    data: dict = Field(default_factory=dict)


class Storyboard(BaseModel):
    """Misma interfaz que render.schemas.Storyboard (la que usa el motor), con los tipos de escena de este agente."""
    topic: str
    language: str = "es"
    voice: str = "em_alex"
    scenes: list[Scene]

    def words(self) -> int:
        return sum(len(s.narration.split()) for s in self.scenes)

    def estimated_seconds(self, words_per_second: float | None = None) -> float:
        wps = words_per_second or get_settings().words_per_second
        return sum(max(s.min_seconds, 0.8 + len(s.narration.split()) / wps) for s in self.scenes)


# ------------------------------------------------------------------ texto para la voz
def _spoken(text: str) -> str:
    """Frase del informe → frase para leer en voz alta: sin citas de página y con las posturas en minúscula."""
    t = re.sub(r"\s*\(p\.\s*\d+\)", "", text or "")
    t = re.sub(r"\s*\((UST10|Stoxx Europe|S&P 500|Topix|Sensex|Bovespa)\)", "", t)   # siglas entre paréntesis del nombre: no se leen
    t = t.replace("rend. objetivo", "rendimiento objetivo").replace("rend. obj.", "rendimiento objetivo")
    t = t.replace("dif. objetivo", "diferencial objetivo").replace("dif. obj.", "diferencial objetivo").replace("bps", "pb")
    t = re.sub(r"\bNEUTRAL\s*-\s*SOBREPONDERAR\b", "neutral a sobreponderar", t)
    t = re.sub(r"\bNEUTRAL\s*-\s*INFRAPONDERAR\b", "neutral a infraponderar", t)
    for w in ("SOBREPONDERAR", "INFRAPONDERAR", "NEUTRAL", "FAVORABLE", "NEGATIVO", "POSITIVA", "SOBREPOND."):
        t = t.replace(w, w.lower().rstrip("."))
    t = t.replace("UST10", "bono del Tesoro a diez años").replace("EE. UU.", "Estados Unidos").replace("EE.UU.", "Estados Unidos")
    t = t.replace("WTI", "W T I")
    t = re.sub(r"\bp(b|bs)\b", "puntos básicos", t)
    for lvl in ("MEDIO-ALTO", "BAJO-MEDIO", "MEDIO", "ALTO", "BAJO"):
        t = t.replace(lvl, lvl.lower().replace("-", " "))
    t = _quarters(t)
    return t[:1].upper() + t[1:] if t else t


def _quarters(t: str) -> str:
    """«4T 2026» → «cuarto trimestre de 2026»: Kokoro lee mal las siglas."""
    ordinal = {"1": "primer", "2": "segundo", "3": "tercer", "4": "cuarto"}
    return re.sub(r"\b([1-4])T\s*(\d{4})", lambda m: f"{ordinal[m.group(1)]} trimestre de {m.group(2)}", t)


def _split_stance(text: str | None) -> tuple[str, str]:
    """«SOBREPONDERAR (rend. objetivo: 5,00%)» → («SOBREPONDERAR», «rend. objetivo: 5,00%»)."""
    if not text:
        return "no figura", ""
    m = re.match(r"\s*([^(]+?)\s*(?:\((.*)\))?\s*$", text)
    return (m.group(1).strip(), (m.group(2) or "").strip()) if m else (text, "")


def _points(c: dict, n: int) -> list[str]:
    """Solo argumentos verificados y cortos, los nuevos primero: en voz no se trunca nada, se elige el que cabe."""
    ok = [p for p in c.get("rationale", []) if p.get("status") in ("publicar", "sin verificar")]
    ok.sort(key=lambda p: not p.get("new"))
    pts = [p["point"].strip() for p in ok if len(p["point"].split()) <= MAX_POINT_WORDS]
    return [p if p.endswith(".") else p + "." for p in pts][:n]


def _first_sentence(text: str) -> str:
    """Primera frase sin la cita de página: en la narración basta el qué; el porqué lo ponen los argumentos."""
    t = re.sub(r"\s*\(p\.\s*\d+\)", "", text or "").strip()
    return t if t.endswith(".") else t + "."


# ------------------------------------------------------------------ guion
def build_storyboard(data: dict, max_points: int = 2, lean: bool = False) -> Storyboard:
    """lean=True: versión corta (sin la escena del oro y con menos texto) para caber en video.max_seconds."""
    s = get_settings()
    prev, curr = data["ediciones"][0], data["ediciones"][1]
    ch = data["cambios"]
    stance = [c for c in ch if c["kind"] == "postura"]
    objetivo = [c for c in ch if c["kind"] == "objetivo"]
    table = [c for c in ch if c["kind"] == "revision_objetivo" and not c["id"].startswith("g:")]
    trends_in = [c for c in ch if c["kind"] == "tendencia_nueva"]
    trends_out = [c for c in ch if c["kind"] == "tendencia_sale"]
    risks = [c for c in ch if c["kind"] == "riesgo"]
    n_targets = len(table) or len(objetivo)                  # la tabla sinóptica ya incluye los del texto
    trend_summary = {t["title"]: t.get("summary", "") for t in data.get("tendencias", {}).get(curr["label"], [])}
    src = f"Opinión Corporativa de Andbank, {curr['label']} ({curr['fecha']})"

    scenes = [Scene(id="portada", kind="title", min_seconds=6, narration=_spoken(
        f"Qué cambia en la Opinión Corporativa de Andbank del {curr['label']} respecto al {prev['label']}, "
        f"y por qué. {len(stance)} cambios de recomendación y {n_targets} objetivos revisados."),
        data={"kicker": "OPINIÓN CORPORATIVA · ANDBANK", "title": f"Qué cambia del {prev['label']} al {curr['label']}",
              "chips": [f"{len(stance)} cambios de recomendación", f"{n_targets} objetivos revisados"],
              "subtitle": "", "ticker": curr["label"], "source": src})]

    for c in stance:
        b_main, b_sub = _split_stance(c["before"]); a_main, a_sub = _split_stance(c["after"])
        pts = _points(c, max_points)
        no_reason = "La casa no detalla el motivo en esta edición."
        why = " ".join(pts) if pts else no_reason                 # mejor decirlo (y enseñarlo) que dejar la escena vacía
        narration = _spoken(_first_sentence(c["explanation"]) + " " + why)
        scenes.append(Scene(id=f"cambio_{c['id'][2:].replace('.', '_')}", kind="shift", min_seconds=6, narration=narration,
                            data={"region": c["group"], "title": c["label"], "before": b_main, "before_main": b_main, "before_sub": b_sub,
                                  "after": a_main, "after_main": a_main, "after_sub": a_sub,
                                  "delta": fmt_delta(c.get("delta"), c.get("delta_unit")) if c.get("delta") is not None else "",
                                  "items": pts or [no_reason], "source": f"{src}, p. {c.get('page_after')}"}))

    # objetivos: los mayores cambios en pb, sin duplicar texto y tabla; el porqué, el del Bund o el primero verificado
    seen, rows = set(), []
    for c in sorted(table or objetivo, key=lambda c: -abs(c.get("delta") or 0)):
        if c.get("delta") is None or c.get("delta_unit") != "pb":
            continue
        key = re.sub(r"[^a-z0-9]", "", c["label"].lower())[:14]
        if key not in seen:
            seen.add(key); rows.append({"label": c["label"], "value": c["delta"], "text": fmt_delta(c["delta"], "pb")})
        if len(rows) == 6:
            break
    if rows:
        pb_rows = [c for c in (table or objetivo) if c.get("delta_unit") == "pb" and c.get("delta") is not None]
        yields = [c for c in pb_rows if "credit" not in (c.get("group") or "").lower()]     # rendimientos, no diferenciales
        up = sum(1 for c in yields if c["delta"] > 0)
        why_src = next((c for c in objetivo if c["id"] == "v:eu.govt_core" and _points(c, 1)), None) or \
            next((c for c in objetivo if _points(c, 1)), None)
        why = [] if lean or why_src is None else _points(why_src, 1)
        head = (f"En renta fija, Andbank eleva {up} de sus {len(yields)} rendimientos objetivo" if up > len(yields) / 2
                else f"En renta fija, Andbank revisa {len(yields)} rendimientos objetivo, {up} al alza")
        narration = _spoken(f"{head}, con la mayor revisión en {rows[0]['label']}: {rows[0]['text']}. " + " ".join(why))
        scenes.append(Scene(id="objetivos", kind="hbars", min_seconds=6, narration=narration,
                            data={"kicker": "Rendimientos objetivo", "title": "Objetivos revisados (puntos básicos)", "rows": rows, "source": src}))

    n_in = min(2, len(trends_in))
    cards = [{"lab": "Entra", "big": c["label"], "tag": (c.get("after") or "").split(",")[0],
              "txt": trend_summary.get(c["label"], "")[:160]} for c in trends_in[:n_in]]
    outs = trends_out[:3 - n_in]                              # hasta tres tarjetas en pantalla: lo que no cabe, se dice en voz
    cards += [{"lab": "Sale", "big": c["label"], "tag": "", "txt": "Deja de figurar en esta edición", "out": True} for c in outs]
    if cards:
        low = lambda t: t[:1].lower() + t[1:]                 # solo la inicial: «LLM» o «IA» se quedan en mayúsculas
        ins = " y ".join(low(c["label"]) for c in trends_in[:n_in])
        same_tone = trends_in and all("FAVORABLE" in (c.get("after") or "").upper() for c in trends_in[:n_in])
        if same_tone:
            narration = _spoken(f"En las tendencias estructurales {'entra' if n_in == 1 else 'entran'} {ins}, "
                                f"{'con opinión favorable' if n_in == 1 else 'ambas con opinión favorable'}.")
        elif trends_in:
            narration = _spoken("En las tendencias estructurales, " + " ".join(_first_sentence(c["explanation"]) for c in trends_in[:n_in]))
        else:
            narration = ""
        if trends_out:
            names = [low(c["label"]) for c in trends_out[:2]]
            narration += _spoken(f" Sale {names[0]}." if len(trends_out) == 1 else
                                 f" Salen {len(trends_out)} temas: {names[0]}; y {names[1]}" + (", entre otros." if len(trends_out) > 2 else "."))
        narration = narration.strip()
        scenes.append(Scene(id="tendencias", kind="cards", min_seconds=6, narration=narration,
                            data={"kicker": "Tendencias estructurales", "title": "Temas que entran y salen", "cards": cards, "source": src}))

    for c in ([] if lean else risks[:1]):
        pts = _points(c, 1)
        scenes.append(Scene(id="oro", kind="shift", min_seconds=6, narration=_spoken(_first_sentence(c["explanation"]) + " " + " ".join(pts)),
                            data={"region": "Oro", "title": c["label"].replace("Riesgo para el oro: ", "Riesgo para el oro · "),
                                  "before": "", "before_main": c["before"], "after": "", "after_main": c["after"], "delta": "",
                                  "items": pts, "source": f"{src}, p. {c.get('page_after')}"}))

    scenes.append(Scene(id="cierre", kind="close", min_seconds=6, narration=(
        "Todos los datos proceden del documento publicado por Andbank y están citados en el informe. "
        "Este vídeo es informativo y no constituye una recomendación personalizada."),
        data={"title": "En resumen", "stats": [{"label": "cambios de recomendación", "value": str(len(stance))},
                                               {"label": "objetivos revisados", "value": str(n_targets)},
                                               {"label": "temas nuevos", "value": str(len(trends_in))}],
              "disclaimer": DISCLAIMER, "source": src}))
    sb = Storyboard(topic=f"Opinión Corporativa {curr['label']}", voice=s.voice, scenes=scenes)
    if sb.estimated_seconds() > s.max_seconds:              # demasiado largo: primero menos razones, luego versión corta
        if max_points > 1:
            return build_storyboard(data, max_points - 1, lean)
        if not lean:
            return build_storyboard(data, 1, True)
    return sb


def make_video(out_dir: Path, log=print) -> Path:
    """Vídeo a partir de la carpeta de una ejecución del agente (la que contiene cambios.json)."""
    import time

    from ...render import video as engine
    from .llmcall import Usage, load_config
    from .tts import narrate

    t0 = time.perf_counter()
    data = json.loads((out_dir / "cambios.json").read_text(encoding="utf-8"))
    sb = build_storyboard(data)
    s = get_settings()
    log(f"  guion: {len(sb.scenes)} escenas · {sb.words()} palabras · ≈ {sb.estimated_seconds():.0f} s (tope {s.max_seconds} s)")
    vid = out_dir / "video"
    vid.mkdir(parents=True, exist_ok=True)
    (vid / "storyboard.json").write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    usage = Usage(load_config())
    tl = narrate(sb, vid, usage, log)
    t1 = time.perf_counter()
    mp4 = engine.render(sb, tl, vid, template=str(TEMPLATE), log=log)
    u = usage.summary()
    stats = {"duracion_s": tl["total"], "voz": tl.get("voice"), "coste_voz_usd": u["coste_usd"], "tokens_audio": u["tokens_salida"],
             "segundos": {"voz": round(t1 - t0, 1), "render": round(time.perf_counter() - t1, 1)}}
    (vid / "estadisticas.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"  vídeo: {tl['total']:.0f} s · voz {stats['voz']} · {u['coste_usd']} $ · voz {stats['segundos']['voz']} s + render {stats['segundos']['render']} s")
    return mp4
