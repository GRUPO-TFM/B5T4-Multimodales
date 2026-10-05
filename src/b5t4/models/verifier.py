"""
Verificador (Jev, de TypeSafe): un modelo que no escribe, juzga. Devuelve probabilidades calibradas.

Dos usos en el MVP:
  supports(claim, passage)  → ¿el pasaje respalda la afirmación? Se usa para que el informe de onboarding, la
                              comparación de opiniones y las respuestas del RAG no digan nada que no esté en
                              los documentos. (Banco de pruebas propio, 2-oct-2026: 11/12, Brier 0,071.)
  is_recommendation(text)   → ¿la frase es una recomendación de inversión personalizada? Puerta de cumplimiento
                              para el vídeo de opinión corporativa. (10/10, Brier 0,017.)

Si no hay JEV_API_KEY, todo devuelve None y los agentes siguen sin verificación (y lo dicen en el log).
"""
from __future__ import annotations

import requests

from ..config import get_settings


def available() -> bool:
    return get_settings().has_verifier


def _ask(state: str, questions: dict) -> dict:
    s = get_settings()
    r = requests.post(s.jev_url, timeout=30, json={"state": state[:24000], "model": s.jev_model, "questions": questions},
                      headers={"Authorization": f"Bearer {s.jev_api_key}", "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"Jev {r.status_code}: {r.text[:200]}")
    d = r.json()
    return d.get("answers", d)


def supports(claim: str, passage: str) -> float | None:
    """Probabilidad de que `passage` respalde `claim` (mismo concepto, mismo periodo, cifras compatibles)."""
    if not available():
        return None
    q = {"ok": {"type": "noul", "instructions": (
        "La AFIRMACIÓN está respaldada por el PASAJE FUENTE: se refiere al mismo concepto y periodo, y las cifras "
        "coinciden admitiendo redondeo razonable. Si el pasaje no lo menciona, NO está respaldada.")}}
    return round(_ask(f"PASAJE FUENTE:\n{passage}\n\nAFIRMACIÓN:\n{claim}", q)["ok"]["noul"], 3)


def is_recommendation(sentence: str) -> float | None:
    """Probabilidad de que la frase sea una recomendación de inversión o incitación a comprar/vender (MiFID II)."""
    if not available():
        return None
    q = {"rec": {"type": "noul", "instructions": (
        "Esta frase constituye una recomendación de inversión personalizada o una incitación a comprar o vender un "
        "valor (en el sentido de MiFID II), y no mera información o descripción de hechos.")}}
    return round(_ask(sentence, q)["rec"]["noul"], 3)


def triage(p: float | None) -> str:
    """Probabilidad → decisión con los umbrales de la configuración."""
    s = get_settings()
    if p is None:
        return "sin verificar"
    return "publicar" if p >= s.publish_threshold else ("descartar" if p < s.discard_threshold else "revisar")
