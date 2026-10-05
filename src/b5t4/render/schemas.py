"""
Contratos de datos del vídeo. El vídeo nunca se «genera» con un modelo de vídeo: se describe como un
storyboard (lista de escenas con datos y locución) y se dibuja de forma determinista. Ventaja: cada cifra
y cada nombre que aparece en pantalla viene del storyboard, que a su vez sale de documentos verificados.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Tipos de escena que sabe dibujar templates/scene.html hoy, más los que necesita el vídeo de onboarding
# (marcados «pendiente»: hay que añadir su bloque de HTML/CSS y su animación en render(t)).
SceneKind = Literal[
    "title", "kpi", "bars", "bullets", "compare", "close",   # existentes (heredadas del prototipo de vídeo)
    "orgchart",   # pendiente: organigrama (consejo → directores → secciones → personas)
    "flow",       # pendiente: diagrama de flujo de un proceso (cajas y flechas que aparecen en orden)
    "people",     # pendiente: rejilla de personas con su rol
    "timeline",   # pendiente: calendario de entregables / evolución de una recomendación entre ediciones
]


class Scene(BaseModel):
    id: str
    kind: SceneKind
    narration: str = Field(..., description="locución de la escena; se verbaliza antes de sintetizar")
    min_seconds: float = 3.0
    data: dict = Field(default_factory=dict, description="lo que la plantilla pinta; depende de `kind`")


class Storyboard(BaseModel):
    topic: str
    language: str = "es"
    voice: str = "em_alex"
    scenes: list[Scene]

    def words(self) -> int:
        return sum(len(s.narration.split()) for s in self.scenes)

    def estimated_seconds(self, words_per_second: float = 2.3) -> float:
        """Presupuesto antes de sintetizar: ~2,3 palabras/s en español. Sirve para recortar el guion a ≤ 2 min."""
        return self.words() / words_per_second + 0.8 * len(self.scenes)
