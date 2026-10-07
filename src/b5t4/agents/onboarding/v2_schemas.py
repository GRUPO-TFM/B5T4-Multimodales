"""Contratos de v2: perfil, referencia editorial y dirección audiovisual verificable."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator

from .schemas import Record, Fact, VerifiedFact


class OnboardingBrief(Record):
    role: str = Field(min_length=3, max_length=200)
    experience: str = Field(default="Se incorpora al equipo", max_length=300)
    objective: str = Field(min_length=10, max_length=1200)
    area: str = Field(default="Gestión Discrecional", max_length=300)
    duration_seconds: int = Field(default=120, ge=60, le=300)
    budget_usd: float = Field(default=5, ge=.10, le=100)
    language: Literal["es-ES"] = "es-ES"
    instructions: str = Field(default="", max_length=3000)
    conversation_id: str = Field(default="", pattern=r"^[a-f0-9-]{0,36}$")


class BriefDraft(Record):
    role: str = ""
    experience: str = "Se incorpora al equipo"
    objective: str = ""
    area: str = "Gestión Discrecional"
    duration_seconds: int = Field(default=120, ge=60, le=300)
    instructions: str = ""

    def missing(self):
        return [label for label, value, minimum in (("puesto", self.role, 3), ("objetivo", self.objective, 10))
                if len(value.strip()) < minimum]


class BriefReply(Record):
    draft: BriefDraft
    message: str = Field(min_length=10, max_length=1800)


class Topic(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,35}$")
    title: str = Field(min_length=3, max_length=100)
    purpose: str = Field(min_length=10, max_length=400)
    common: bool = False
    sources: list[str] = Field(min_length=1, max_length=4)
    sections: list[str] = Field(min_length=1, max_length=11)
    document_paths: list[str] = Field(default_factory=list, max_length=3)


class ResearchPlan(Record):
    title: str = Field(min_length=5, max_length=140)
    chapters: list[Topic] = Field(min_length=6, max_length=10)

    @model_validator(mode="after")
    def core(self):
        if len({c.id for c in self.chapters}) != len(self.chapters):
            raise ValueError("Los capítulos deben tener identificadores únicos")
        if not {"team", "organisation", "rules", "resources"} <= {c.id for c in self.chapters if c.common}:
            raise ValueError("Faltan los capítulos comunes team, organisation, rules y resources")
        return self


class ResearchDraft(Record):
    facts: list[Fact] = Field(min_length=4, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=6)


class FactChapter(Record):
    id: str
    title: str
    purpose: str
    common: bool
    facts: list[VerifiedFact]
    gaps: list[str] = Field(default_factory=list)


class FactBank(Record):
    title: str
    chapters: list[FactChapter]

    def published(self):
        return {fact.id: fact for chapter in self.chapters for fact in chapter.facts if fact.status == "publicar"}


class CitedText(Record):
    text: str = Field(min_length=10, max_length=1800)
    claim_ids: list[str] = Field(min_length=1, max_length=8)


class TableRow(Record):
    label: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=5, max_length=400)
    claim_ids: list[str] = Field(min_length=1, max_length=5)


class GuideChapter(Record):
    id: str
    title: str = Field(min_length=3, max_length=100)
    paragraphs: list[CitedText] = Field(min_length=3, max_length=6)
    table_title: str = ""
    rows: list[TableRow] = Field(default_factory=list, max_length=6)


class ReferenceGuide(Record):
    title: str
    chapters: list[GuideChapter]


class Review(Record):
    clarity: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    coherence: int = Field(ge=1, le=5)
    issues: list[str] = Field(default_factory=list, max_length=10)
    affected_ids: list[str] = Field(default_factory=list, max_length=24)

    def passes(self):
        return min(self.clarity, self.relevance, self.coherence) >= 4 and not self.issues


class VisualItem(Record):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,35}$")
    label: str = Field(min_length=1, max_length=70)
    detail: str = Field(default="", max_length=160)
    claim_ids: list[str] = Field(min_length=1, max_length=5)


class Edge(Record):
    from_id: str
    to_id: str
    label: str = Field(default="", max_length=60)
    claim_ids: list[str] = Field(min_length=1, max_length=6)


VisualKind = Literal["hero", "organisation", "map", "process", "timeline", "illustration", "focus", "close"]


class VisualModule(Record):
    kind: VisualKind
    title: str = Field(min_length=3, max_length=90)
    items: list[VisualItem] = Field(min_length=1, max_length=6)
    edges: list[Edge] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def connections(self):
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Los nodos del módulo deben ser únicos")
        if any(edge.from_id not in ids or edge.to_id not in ids or edge.from_id == edge.to_id for edge in self.edges):
            raise ValueError("Las relaciones deben unir nodos distintos presentes en el módulo")
        if self.kind == "organisation" and not self.edges:
            # Sin relaciones documentadas no hay jerarquía que dibujar: los mismos nodos
            # se muestran como mapa sin conectores, igual que cuando Jev rechaza una relación.
            self.kind = "map"
        return self


class Illustration(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,35}$")
    subject: str = Field(min_length=10, max_length=400)
    purpose: str = Field(min_length=10, max_length=300)


class Direction(Record):
    narrative_arc: str = Field(min_length=20, max_length=1000)
    learning_goals: list[str] = Field(min_length=2, max_length=6)
    modules: list[VisualModule] = Field(min_length=4, max_length=6)
    illustrations: list[Illustration] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_illustrations(self):
        if len({image.id for image in self.illustrations}) != len(self.illustrations):
            raise ValueError("Las ilustraciones deben tener ids únicos")
        return self


class DirectedScene(VisualModule):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,35}$")
    narration: str = Field(min_length=30, max_length=1600)
    claim_ids: list[str] = Field(min_length=1, max_length=10)
    image_id: str = ""
    transition: Literal["fade", "diagonal", "slide"] = "fade"
    movement: Literal["reveal", "trace", "focus"] = "reveal"

    @model_validator(mode="after")
    def readable(self):
        if self.kind in ("organisation", "process") and len(self.items) > 4:
            raise ValueError("Los diagramas del vídeo admiten hasta cuatro nodos por escena")
        if self.kind == "organisation":
            if any(len(item.detail) > 90 for item in self.items):
                raise ValueError("Acorta el detalle de cada nodo de organigrama a 90 caracteres")
            parents = {}
            for edge in self.edges:
                if edge.to_id in parents:
                    raise ValueError("Un nodo de jerarquía no puede tener dos superiores en este diagrama")
                parents[edge.to_id] = edge.from_id
            for node in parents:
                seen = set()
                while node in parents:
                    if node in seen:
                        raise ValueError("La jerarquía contiene un ciclo")
                    seen.add(node); node = parents[node]
        return self


class DirectedStoryboard(Record):
    scenes: list[DirectedScene] = Field(min_length=4, max_length=24)

    @model_validator(mode="after")
    def structure(self):
        if len({scene.id for scene in self.scenes}) != len(self.scenes):
            raise ValueError("Las escenas deben tener ids únicos")
        if self.scenes[0].kind != "hero" or self.scenes[-1].kind != "close":
            raise ValueError("El vídeo necesita una apertura hero y un cierre close")
        if len({scene.kind for scene in self.scenes}) < 3:
            raise ValueError("El vídeo necesita variedad de composición")
        return self


class NarrationRevision(Record):
    scenes: list[CitedText]


class AudioReview(Record):
    transcript: str
    clarity: int = Field(ge=1, le=5)
    naturalness: int = Field(ge=1, le=5)
    complete: bool
    issues: list[str] = Field(default_factory=list, max_length=8)
