"""
AGENTE 2 · Evolución de la Opinión Corporativa: «¿qué ha cambiado en la visión de la casa?».

Entrada : los PDF de la Opinión Corporativa (config: corpus.opinion_dir), dos o más ediciones.
Salidas : out/opinion/<fecha>/ informe.html + informe.md (cambios por país y activo, con cita de página)
          · video.mp4 (solo los cambios, ~60-90 s) · cambios.json

Flujo:
  1. list_editions()        [hecho]  PDF de la carpeta → ediciones ordenadas por fecha (la fecha va en el nombre).
  2. extract_views()        [LLM]    por edición, el texto de cada bloque «Perspectivas de mercado: recomendaciones
                                     y objetivos» → filas EditionView (región, activo, postura, objetivo, página).
                                     Las páginas sin texto útil (gráficos, tablas en imagen) se rasterizan con
                                     corpus.pdf_page_images y se leen con llm.ask_vision → multimodalidad real.
  3. compare()              [hecho cuando 2 exista]  diff determinista entre ediciones consecutivas: cambio de postura
                                     (INFRAPONDERAR → NEUTRAL…), cambio de objetivo, activo nuevo o desaparecido.
                                     El LLM NO compara: compara Python, el LLM solo explica.
  4. explain()              [LLM]    para cada cambio, el porqué en el texto de la edición nueva (pasaje citado);
                                     verificado con Jev (supports) y puerta de cumplimiento (is_recommendation).
  5. render                          informe (tabla de cambios + explicación) y storyboard (escenas timeline/compare).

Referencia para validar: `03. Vision Corporativa y Servicio/01. Opinion Corporativa/00_EVOLUCION_RECOMENDACIONES.md`
ya recoge a mano las recomendaciones de las 4 ediciones: es el «golden set» del paso 2.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ...config import get_settings

Stance = Literal["SOBREPONDERAR", "NEUTRAL-SOBREPONDERAR", "NEUTRAL", "NEUTRAL-INFRAPONDERAR", "INFRAPONDERAR",
                 "FAVORABLE", "NEGATIVO", "OTRA"]


# ---------------------------------------------------------------------------------- contratos
class Edition(BaseModel):
    date: dt.date
    label: str          # «Octubre 2025», «Visión Estratégica 2026», «3T 2026»…
    path: Path


class EditionView(BaseModel):
    edition: str
    region: str = Field(..., description="EE.UU., Europa, China, Japón, India, Israel, Brasil, México, Argentina")
    asset: str = Field(..., description="p. ej. «Renta variable (S&P)», «Deuda soberana (UST 10 años)»")
    stance: Stance
    stance_raw: str = Field(..., description="texto literal de la postura en el PDF")
    target: Optional[str] = Field(None, description="objetivo numérico literal, p. ej. «rend. objetivo: 5,00 %»")
    page: int


class Change(BaseModel):
    region: str
    asset: str
    before: Optional[EditionView]
    after: Optional[EditionView]
    kind: Literal["postura", "objetivo", "nuevo", "desaparece"]


# ---------------------------------------------------------------------------------- paso 1 (hecho)
def list_editions() -> list[Edition]:
    """Ediciones disponibles, de la más antigua a la más reciente. El nombre es «AAAA-MM-DD_Opinion_Corporativa_<edición>.pdf»."""
    s = get_settings()
    eds = []
    for p in sorted(s.opinion_path.glob("*.pdf")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_Opinion_Corporativa_(.+)\.pdf$", p.name)
        if m:
            label = m.group(2).replace("_", " ").replace("Mensual ", "").strip()
            eds.append(Edition(date=dt.date.fromisoformat(m.group(1)), label=label, path=p))
    return sorted(eds, key=lambda e: e.date)


# ---------------------------------------------------------------------------------- pasos 2-5 (pendientes)
def extract_views(edition: Edition) -> list[EditionView]:
    raise NotImplementedError("Paso 2 pendiente: texto de los bloques de recomendación → llm.ask_json(list[EditionView]); "
                              "visión para páginas sin texto.")


def compare(before: list[EditionView], after: list[EditionView]) -> list[Change]:
    raise NotImplementedError("Paso 3 pendiente: diff determinista por (región, activo).")


def run(out_root: Path | None = None, log=print) -> Path:
    s = get_settings()
    out = (out_root or s.out_dir / "opinion") / dt.datetime.now().strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)
    eds = list_editions()
    log(f"1 ediciones: {len(eds)} → " + " · ".join(f"{e.date} {e.label}" for e in eds))
    extract_views(eds[0])    # → NotImplementedError hasta que se implemente
    return out
