"""
AGENTE 1 · Onboarding: «explícame el equipo como si fuera mi primer día».

Entrada : la carpeta de la empresa (los `00_CONTEXTO.md` y, cuando haga falta, los documentos que citan).
Salidas : out/onboarding/<fecha>/ informe.html + informe.md · infografia.png · video.mp4 (≤ 2 min) · storyboard.json

Flujo (determinista salvo los pasos marcados LLM):
  1. gather_material()   [hecho]  secciones 1-5 de cada contexto (qué es, responsables, objetivos,
                                  entregables, procesos) → un dosier ordenado por carpeta, con su ruta de origen.
  2. plan_outline()      [LLM]    dosier → índice del onboarding (OnboardingOutline): 6-9 bloques en el orden en
                                  que se lo contarías a alguien nuevo (el banco → el equipo y su jerarquía →
                                  las secciones → quién hace qué → el calendario → las reglas → dónde está todo).
  3. write_report()      [LLM]    índice + dosier → informe en Markdown; cada afirmación lleva su fuente.
  4. verify()            [Jev]    cada afirmación contra su pasaje fuente; lo dudoso se marca o se quita.
  5. build_storyboard()  [LLM]    índice → escenas (orgchart, people, flow, timeline, bullets) con locución;
                                  presupuesto de ≤ 120 s ≈ 250 palabras de locución en total.
  6. render              [hecho]  render.report.write_report · render.infographic (pendiente) · render.video.make_video

Regla de oro (heredada del prototipo): el informe verificado es la ÚNICA fuente de la infografía y del vídeo.
Ni la infografía ni el vídeo vuelven a leer documentos ni inventan nombres o cifras.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import BaseModel, Field

from ...config import get_settings
from ...corpus import load_contexts

# Secciones de la plantilla de contexto que alimentan el onboarding (1 Qué es … 5 Procesos)
ONBOARDING_SECTIONS = ("1", "2", "3", "4", "5")


# ---------------------------------------------------------------------------------- contratos
class OutlineBlock(BaseModel):
    title: str = Field(..., description="título del bloque, p. ej. «Quién decide: la jerarquía»")
    key_points: list[str] = Field(..., min_length=2, max_length=6)
    sources: list[str] = Field(..., description="rutas de los 00_CONTEXTO.md usados")
    scene_kind: str = Field(..., description="orgchart | people | flow | timeline | bullets | title | close")


class OnboardingOutline(BaseModel):
    title: str
    audience: str = "nuevo empleado del equipo de Gestión Discrecional"
    blocks: list[OutlineBlock] = Field(..., min_length=5, max_length=10)


# ---------------------------------------------------------------------------------- paso 1 (hecho)
def gather_material(max_chars_per_section: int = 3500) -> str:
    """Dosier de partida para el LLM: las secciones 1-5 de cada contexto, etiquetadas con su origen.
    Se recorta cada sección para que el dosier completo quepa holgado en el contexto de un modelo barato."""
    parts = []
    for doc in load_contexts():
        blocks = []
        for sec in doc.sections:
            if sec.number in ONBOARDING_SECTIONS:
                txt = sec.text if len(sec.text) <= max_chars_per_section else sec.text[:max_chars_per_section] + " […]"
                blocks.append(f"### §{sec.number} {sec.title}\n{txt}")
        if blocks:
            parts.append(f"## {doc.title}\n_Fuente: {doc.rel}_\n\n" + "\n\n".join(blocks))
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------------- pasos 2-6 (pendientes)
def plan_outline(material: str) -> OnboardingOutline:
    raise NotImplementedError("Paso 2 pendiente: llm.ask_json(OnboardingOutline, …) con el dosier de gather_material().")


def run(out_root: Path | None = None, log=print) -> Path:
    """Ejecuta el agente completo y devuelve la carpeta de salida."""
    s = get_settings()
    out = (out_root or s.out_dir / "onboarding") / dt.datetime.now().strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)
    material = gather_material()
    (out / "dosier.md").write_text(material, encoding="utf-8")
    log(f"1 dosier: {len(material):,} caracteres → {out / 'dosier.md'}")
    plan_outline(material)   # → NotImplementedError hasta que se implemente
    return out
