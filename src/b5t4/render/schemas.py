"""
Contratos de datos del vídeo. El vídeo nunca se «genera» con un modelo de vídeo: se describe como un
storyboard (lista de escenas con datos y locución) y se dibuja de forma determinista. Ventaja: cada cifra
y cada nombre que aparece en pantalla viene del storyboard, que a su vez sale de documentos verificados.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Tipos de escena dibujados por templates/scene.html. Las escenas del prototipo conservan sus contratos.
SceneKind = Literal[
    "title", "kpi", "bars", "bullets", "compare", "close",   # existentes (heredadas del prototipo de vídeo)
    "orgchart",   # niveles de jerarquía
    "flow",       # pasos numerados de un proceso
    "people",     # rejilla de personas/secciones con su rol
    "timeline",   # cadencias y entregables
    "hero", "organisation", "map", "process", "illustration", "focus",
]


class Scene(BaseModel):
    id: str
    kind: SceneKind
    narration: str = Field(..., description="locución de la escena; se verbaliza antes de sintetizar")
    min_seconds: float = 3.0
    data: dict = Field(default_factory=dict, description="lo que la plantilla pinta; depende de `kind`")

    @model_validator(mode="after")
    def validate_onboarding_layout(self):
        if self.data.get("layout") == "onboarding_v2":
            from ..agents.onboarding.v2_schemas import DirectedScene
            DirectedScene.model_validate({"id": self.id, "kind": self.kind, "narration": self.narration,
                                          **{k: v for k, v in self.data.items() if k in DirectedScene.model_fields}})
            return self
        if self.kind in ("orgchart", "people", "flow", "timeline") or self.data.get("layout") == "onboarding":
            if not isinstance(self.data.get("title"), str) or not self.data["title"].strip():
                raise ValueError("Una escena de onboarding necesita un título")
            items = self.data.get("items")
            if not isinstance(items, list) or not 2 <= len(items) <= 7:
                raise ValueError("Una escena de onboarding necesita entre 2 y 7 tarjetas")
            if self.kind == "orgchart" and len(items) > 3:
                raise ValueError("El organigrama del vídeo admite un máximo de tres niveles")
            if self.kind == "flow" and len(items) > 4:
                raise ValueError("El proceso del vídeo admite un máximo de cuatro pasos resumidos")
            for item in items:
                if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("label", "detail")):
                    raise ValueError("Cada tarjeta necesita label y detail")
        return self


class Storyboard(BaseModel):
    topic: str
    language: str = "es"
    voice: str = "em_alex"
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("Los identificadores de escena deben ser únicos")
        return self

    def words(self) -> int:
        return sum(len(s.narration.split()) for s in self.scenes)

    def estimated_seconds(self, words_per_second: float = 2.3) -> float:
        """Presupuesto antes de sintetizar: ~2,3 palabras/s en español. Sirve para recortar el guion a ≤ 2 min."""
        return self.words() / words_per_second + 0.8 * len(self.scenes)
