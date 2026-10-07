"""Conversación por sesión: comprender → completar lo necesario → confirmar una sola vez."""
from __future__ import annotations
import copy
import json
from uuid import uuid4

from ...config import get_settings
from ...models.openrouter import OpenRouter, write_json
from ...render.brand import RULES
from .v2_schemas import BriefReply, OnboardingBrief


def new_session():
    return {"id": str(uuid4()), "history": [], "draft": None, "confirmed": False}


def chat(message: str, state: dict | None = None, log=lambda _: None):
    state = copy.deepcopy(state) if state else new_session()
    if state.get("confirmed"):
        state = new_session()
    state["history"].append({"role": "user", "content": message.strip()})
    client = OpenRouter(get_settings().out_dir / "onboarding" / "drafts" / state["id"],
                        get_settings().onboarding_budget, log)
    system = ("Eres el interlocutor de onboarding de Gestión Discrecional de Andbank España. "
              "Comprende puesto, experiencia, objetivo y área. Pregunta SOLO por puesto u objetivo si faltan; "
              "experiencia inicial, área Gestión Discrecional y 120 segundos son valores por defecto. "
              "No inventes datos de la persona. Duración permitida 60-300 segundos. Mantén las preferencias "
              "anteriores salvo corrección explícita. Agrupa las preguntas necesarias. Cuando tengas puesto "
              "y objetivo, resume el encargo e indica que puede editar los campos y confirmarlo. No prometas "
              "generación antes de confirmar ni respondas consultas corporativas con datos no consultados. "
              "instructions recoge SOLO preferencias de contenido, nunca cambios de identidad visual. "
              "Si piden otra estética, explica brevemente que se aplicará la identidad corporativa Andbank; "
              "no enumeres códigos de color ni detalles técnicos en la conversación. " + RULES)
    def validate(reply):
        if reply.draft.missing(): return
        from .v2_content import Checks
        checks = Checks(client.out, get_settings().out_dir / "onboarding" / "cache" / "comprobaciones.json", log)
        user_text = "\n".join(entry["content"] for entry in state["history"] if entry["role"] == "user")
        checks.require([(f"El onboarding solicitado está dirigido a: {reply.draft.role}", user_text),
                        (f"El objetivo solicitado es: {reply.draft.objective}", user_text)],
                       ["interpretación del puesto", "interpretación del objetivo"])
    response = client.json(BriefReply, system, json.dumps(state["history"], ensure_ascii=False),
                           stage="comprensión del encargo", max_output=2200, validate=validate)
    state["draft"] = response.draft.model_dump()
    state["history"].append({"role": "assistant", "content": response.message})
    write_json(client.out / "conversacion.json", state)
    return state, response


def confirm(state, *, role, experience, objective, area, minutes, budget=5):
    if not state or not state.get("draft"):
        raise ValueError("Describe primero el encargo en la conversación")
    brief = OnboardingBrief(role=role.strip(), experience=experience.strip(), objective=objective.strip(),
                            area=area.strip(), duration_seconds=round(float(minutes) * 60), budget_usd=budget,
                            instructions=state["draft"].get("instructions", ""), conversation_id=state["id"])
    result = copy.deepcopy(state)
    result["confirmed"] = True
    return result, brief
