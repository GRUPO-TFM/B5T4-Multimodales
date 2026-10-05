"""
Adaptador del LLM (OpenRouter). Tres operaciones y ninguna más:

  ask_text(...)    → texto libre (guiones, respuestas redactadas)
  ask_json(...)    → JSON validado contra un esquema Pydantic; si no valida, reintenta una vez con el error
  ask_vision(...)  → lo mismo, pero con imágenes adjuntas (páginas de PDF rasterizadas, gráficos)

Por qué JSON + Pydantic: lo que escribe un modelo se trata como una entrada no fiable. Si el JSON no cumple el
esquema, no pasa a la siguiente etapa. Esto convierte «el LLM se ha inventado un campo» en un error visible.

Por qué OpenRouter: una sola clave da acceso a cualquier modelo; se cambia de modelo en config/b5t4.toml
sin tocar código, y por defecto se usan los baratos (DeepSeek / Gemini Flash).
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from ..config import get_settings

T = TypeVar("T", bound=BaseModel)


def _post(model: str, messages: list[dict], json_mode: bool) -> tuple[str, dict]:
    s = get_settings()
    if not s.openrouter_api_key:
        raise RuntimeError("Falta OPENROUTER_API_KEY (ponla en .env o como variable de entorno).")
    payload = {"model": model, "temperature": s.temperature, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(s.llm_url, timeout=240, json=payload, headers={
        "Authorization": f"Bearer {s.openrouter_api_key}", "Content-Type": "application/json",
        "X-Title": "MIAX B5-T4"})
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def _extract_json(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        s = s[4:] if s.startswith("json") else s
    i, j = s.find("{"), s.rfind("}")
    return json.loads(s[i: j + 1])


def _schema_hint(schema: Type[BaseModel]) -> str:
    return ("\n\nResponde ÚNICAMENTE con un objeto JSON válido que cumpla este esquema (JSON Schema):\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False))


def ask_text(system: str, user: str, model: str | None = None, log=print) -> str:
    model = model or get_settings().model_main
    txt, usage = _post(model, [{"role": "system", "content": system}, {"role": "user", "content": user}], False)
    log(f"  llm {model}: {usage.get('prompt_tokens', '?')} → {usage.get('completion_tokens', '?')} tokens")
    return txt


def ask_json(schema: Type[T], system: str, user: str, model: str | None = None, log=print) -> T:
    model = model or get_settings().model_main
    msgs = [{"role": "system", "content": system + _schema_hint(schema)}, {"role": "user", "content": user}]
    txt, usage = _post(model, msgs, True)
    log(f"  llm {model}: {usage.get('prompt_tokens', '?')} → {usage.get('completion_tokens', '?')} tokens")
    try:
        return schema.model_validate(_extract_json(txt))
    except (ValidationError, ValueError) as e:
        log(f"  llm: JSON no válido ({str(e)[:120]}), reintento")
        msgs.append({"role": "assistant", "content": txt})
        msgs.append({"role": "user", "content": f"Tu respuesta no cumplía el esquema: {str(e)[:800]}\nCorrígela."})
        txt, _ = _post(model, msgs, True)
        return schema.model_validate(_extract_json(txt))


def _image_part(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def ask_vision(schema: Type[T], system: str, user: str, images: list[Path], model: str | None = None, log=print) -> T:
    """Como ask_json, con imágenes. Uso típico: una página de la Opinión Corporativa → tabla de recomendaciones."""
    model = model or get_settings().model_vision
    content = [{"type": "text", "text": user}] + [_image_part(p) for p in images]
    msgs = [{"role": "system", "content": system + _schema_hint(schema)}, {"role": "user", "content": content}]
    txt, usage = _post(model, msgs, True)
    log(f"  vision {model}: {len(images)} imágenes · {usage.get('prompt_tokens', '?')} → {usage.get('completion_tokens', '?')} tokens")
    return schema.model_validate(_extract_json(txt))
