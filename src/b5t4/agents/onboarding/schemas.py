"""Contratos del onboarding: las referencias se conservan hasta las salidas finales."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TOPICS = ("overview", "people", "sections", "portfolios", "processes", "calendar", "rules", "resources")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Record):
    id: str
    source: str
    heading: str
    text: str
    page: int = 1
    section: str = ""
    kind: Literal["context", "document"] = "context"


class OutlineBlock(Record):
    id: Literal["overview", "people", "sections", "portfolios", "processes", "calendar", "rules", "resources"]
    title: str = Field(min_length=3, max_length=100)
    key_points: list[str] = Field(min_length=2, max_length=6)
    sources: list[str] = Field(min_length=1, max_length=5, description="Rutas exactas de contextos del catálogo")
    sections: list[str] = Field(min_length=1, max_length=11, description="Apartados de contexto necesarios, de 1 a 11")
    document_paths: list[str] = Field(default_factory=list, max_length=4, description="Rutas exactas de documentos del catálogo")
    scene_kind: Literal["orgchart", "people", "flow", "timeline", "bullets"] = "bullets"


class OnboardingOutline(Record):
    title: str = Field(min_length=5, max_length=120)
    audience: str = "nuevo empleado del equipo de Gestión Discrecional"
    blocks: list[OutlineBlock] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def complete_topics(self):
        if {b.id for b in self.blocks} != set(TOPICS):
            raise ValueError("El índice debe cubrir una vez cada uno de los ocho temas requeridos")
        if any(not set(b.sections) <= {str(i) for i in range(1, 12)} for b in self.blocks):
            raise ValueError("Los apartados deben ser números entre 1 y 11")
        return self


class Fact(Record):
    text: str = Field(min_length=10, max_length=700)
    source_ids: list[str] = Field(min_length=1, max_length=3)


class BlockDraft(Record):
    facts: list[Fact] = Field(min_length=3, max_length=7)
    gaps: list[str] = Field(default_factory=list, max_length=6)


class FocusedFact(Fact):
    text: str = Field(min_length=10, max_length=300, description="Una sola afirmación breve, sin unir hechos diferentes")
    source_ids: list[str] = Field(min_length=1, max_length=1)


class SourceSelection(Record):
    document_paths: list[str] = Field(default_factory=list, max_length=3)


class VerifiedFact(Fact):
    id: str
    probability: float | None = None
    status: Literal["publicar", "revisar", "descartar", "sin verificar"]
    error: str | None = None
    corrections: int = 0


class ReportBlock(Record):
    id: str
    title: str
    facts: list[VerifiedFact]
    gaps: list[str] = Field(default_factory=list)


class VerifiedReport(Record):
    title: str
    audience: str
    blocks: list[ReportBlock]

    def published(self) -> list[VerifiedFact]:
        return [f for b in self.blocks for f in b.facts if f.status == "publicar"]


class VisualItem(Record):
    label: str = Field(min_length=1, max_length=65)
    detail: str = Field(min_length=1, max_length=160)
    claim_ids: list[str] = Field(min_length=1, max_length=3)


class VisualBlock(Record):
    kind: Literal["orgchart", "people", "flow", "timeline", "bullets"]
    title: str = Field(min_length=3, max_length=80)
    items: list[VisualItem] = Field(min_length=2, max_length=7)


class InfographicPlan(Record):
    blocks: list[VisualBlock] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def required_views(self):
        if {b.kind for b in self.blocks} != {"orgchart", "people", "flow", "timeline"}:
            raise ValueError("Se necesitan organigrama, mapa de secciones/personas, proceso y calendario")
        return self


class NarratedScene(Record):
    kind: Literal["orgchart", "people", "flow", "timeline", "bullets"]
    title: str = Field(min_length=3, max_length=80)
    narration: str = Field(min_length=20, max_length=650)
    claim_ids: list[str] = Field(min_length=1, max_length=6)
    items: list[VisualItem] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def readable_hierarchy(self):
        if self.kind == "orgchart" and len(self.items) > 3:
            raise ValueError("El organigrama del vídeo admite un máximo de tres niveles")
        if self.kind == "flow" and len(self.items) > 4:
            raise ValueError("El proceso del vídeo admite un máximo de cuatro pasos resumidos")
        return self


class VideoPlan(Record):
    scenes: list[NarratedScene] = Field(min_length=6, max_length=8)

    @model_validator(mode="after")
    def word_budget(self):
        words = sum(len(s.narration.split()) for s in self.scenes)
        if not 120 <= words <= 250:
            raise ValueError(f"La locución debe tener entre 120 y 250 palabras; tiene {words}")
        return self
