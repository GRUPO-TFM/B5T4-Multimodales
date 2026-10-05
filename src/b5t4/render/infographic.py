"""
Infografía (pendiente — agente 1): una página con diagramas de flujo y organigrama, exportable a PNG/PDF.

Propuesta (sin modelos generativos de imagen, que inventan texto y cifras):
  1. el agente produce los diagramas en Mermaid (organigrama, flujo semanal/mensual, mapa de secciones);
  2. una plantilla HTML los pinta con mermaid.js (vía CDN o empaquetado) junto a tarjetas de datos;
  3. Playwright captura la página a PNG (y a PDF con page.pdf()).
El mismo HTML sirve de pieza del informe y de fondo para escenas del vídeo.

Interfaz que espera el agente de onboarding (no cambiarla al implementar):
    write_infographic(blocks: list[dict], title: str, out: Path) -> Path   # devuelve el PNG
"""
from __future__ import annotations

from pathlib import Path


def write_infographic(blocks: list[dict], title: str, out: Path) -> Path:
    raise NotImplementedError("Infografía pendiente: ver docstring del módulo.")
