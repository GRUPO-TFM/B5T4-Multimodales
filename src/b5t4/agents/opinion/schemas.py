"""
Contratos de datos del agente 2. Todo lo que escribe un LLM se valida contra estos esquemas antes de seguir,
y la comparación trabaja solo con ellos: nunca con texto libre.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Posturas de la casa, de más negativa a más positiva. El orden permite decir si un cambio «mejora» o «empeora».
STANCE_ORDER = ["NEGATIVO", "INFRAPONDERAR", "NEUTRAL-INFRAPONDERAR", "NEUTRAL", "NEUTRAL-SOBREPONDERAR",
                "SOBREPONDERAR", "FAVORABLE"]
Stance = Literal["NEGATIVO", "INFRAPONDERAR", "NEUTRAL-INFRAPONDERAR", "NEUTRAL", "NEUTRAL-SOBREPONDERAR",
                 "SOBREPONDERAR", "FAVORABLE", "OTRA"]


class Edition(BaseModel):
    date: dt.date
    label: str                       # «3T 2026», «Visión Estratégica 2026»…
    path: Path
    md5: str = ""


# ------------------------------------------------------------------ lo que se extrae de cada edición
class View(BaseModel):
    """Una recomendación de un bloque «Perspectivas de mercado: recomendaciones y objetivos»."""
    asset_id: str = Field(..., description="identificador canónico del catálogo (p. ej. «us.govt10y»); «otro:<slug>» si no está")
    label: str = Field(..., description="nombre legible en español, p. ej. «Bono del Tesoro de EE.UU. a 10 años»")
    region: str
    stance: Stance
    stance_raw: str = Field(..., description="postura literal del PDF")
    target_raw: Optional[str] = Field(None, description="objetivo literal, p. ej. «rend. objetivo: 5,00%»")
    target_value: Optional[float] = Field(None, description="objetivo como número (5.0); null si no hay o hay varios")
    target_unit: Optional[str] = Field(None, description="«%», «pb», «nivel» o «tipo de cambio»")
    page: int
    evidence: Optional[str] = Field(None, description="línea literal del PDF que respalda la fila (la busca Python, no el LLM)")
    table_check: Optional[str] = Field(None, description="cruce con la tabla sinóptica: «coincide», «difiere» o None si no aplica")


class TargetRow(BaseModel):
    """Una fila de la «Tabla sinóptica de rentabilidades esperadas» (página en imagen → modelo de visión)."""
    asset_class: str = Field(..., description="p. ej. «Equity», «Fixed Income Core countries», «Fx»")
    index: str = Field(..., description="nombre literal de la fila, p. ej. «US Treasury 10 year Govie»")
    current: Optional[float] = None
    target: Optional[float] = Field(None, description="«Andbank's Target Price Year End»")
    expected_perf: Optional[float] = Field(None, description="rentabilidad esperada en %, con signo")
    revision: Literal["al alza", "a la baja", "sin marcar"] = Field(
        "sin marcar", description="color del objetivo en la tabla: verde = al alza, rojo = a la baja")
    consistent: Optional[bool] = Field(None, description="Python: ¿expected_perf ≈ target/current − 1? (solo índices, divisas y materias primas)")


class Trend(BaseModel):
    title: str = Field(..., description="tema de la tendencia estructural, breve")
    conclusion: str = Field(..., description="POSITIVA, NEUTRAL, FAVORABLE, NEGATIVA…, en mayúsculas")
    summary: str = Field(..., description="la conclusión en una frase, fiel al texto")
    page: int
    evidence: Optional[str] = None


class Risk(BaseModel):
    """Riesgos calificados del oro (BAJO / MEDIO / ALTO…)."""
    risk: str
    level: str
    page: int


class EditionData(BaseModel):
    edition: Edition
    views: list[View] = Field(default_factory=list)
    targets: list[TargetRow] = Field(default_factory=list)
    trends: list[Trend] = Field(default_factory=list)
    gold_risks: list[Risk] = Field(default_factory=list)
    pages: dict[int, str] = Field(default_factory=dict, description="texto por página (para citar y verificar)")
    table_page: Optional[int] = None
    table_image: Optional[str] = Field(None, description="PNG de la página de la tabla sinóptica (para enseñar la fuente)")
    usage: dict = Field(default_factory=dict, description="tokens y coste de la extracción")


# ------------------------------------------------------------------ la comparación
ChangeKind = Literal["postura", "objetivo", "nuevo", "desaparece", "revision_objetivo",
                     "tendencia_nueva", "tendencia_sale", "tendencia_conclusion", "riesgo"]


class Change(BaseModel):
    id: str
    kind: ChangeKind
    group: str = Field(..., description="región o bloque: «EE.UU.», «Europa», «Tendencias», «Tabla de objetivos»…")
    label: str
    before: Optional[str] = None
    after: Optional[str] = None
    direction: Literal["mejora", "empeora", "al alza", "a la baja", "neutro"] = "neutro"
    delta: Optional[float] = None
    delta_unit: Optional[str] = None
    page_after: Optional[int] = None
    page_before: Optional[int] = None
    importance: int = Field(2, description="1 = titular (cambio de postura), 2 = relevante, 3 = detalle")
    explanation: Optional[str] = None
    support: Optional[float] = Field(None, description="Jev: probabilidad de que la página respalde la explicación")
    advice_risk: Optional[float] = Field(None, description="Jev: probabilidad de que la frase suene a recomendación personalizada")
    status: str = "sin verificar"
    evidence_before: Optional[str] = None
    evidence_after: Optional[str] = None
    checks: list[str] = Field(default_factory=list, description="comprobaciones superadas o avisos (sin LLM)")
    rationale: list[dict] = Field(default_factory=list, description="el porqué según la casa: [{point, quote, page, support, status}]")
