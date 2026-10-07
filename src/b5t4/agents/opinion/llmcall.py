"""
Cliente de OpenRouter propio del agente 2. Es deliberadamente pequeño y vive aquí (y no en models/llm.py) para no
tocar la capa común mientras los otros agentes se desarrollan en paralelo. Lo que añade sobre models/llm.py:

  · reasoning desactivado  → Gemini Flash «piensa» antes de contestar si no se le dice lo contrario: para extraer
                             datos de un texto eso cuesta tokens de salida (hasta ×4) y segundos, sin mejorar nada.
  · contador de tokens     → cada ejecución sabe cuánto ha costado (se imprime y va al informe).
  · modelos configurables  → sección [opinion] de config/b5t4.toml (sin tocar config.py).

Cuando se consolide, se funde en models/llm.py añadiendo un parámetro `extra` a `_post`.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from ...config import CONFIG_FILE, get_settings

T = TypeVar("T", bound=BaseModel)

# Precios de OpenRouter (USD por millón de tokens, consultados el 7-oct-2026): solo para ESTIMAR el coste.
DEFAULT_PRICES = {"google/gemini-3.8-flash": (0.75, 3.75), "deepseek/deepseek-v4.1-flash": (0.055, 1.32)}


@dataclass
class OpinionConfig:
    model_text: str
    model_vision: str
    reasoning: str = "none"           # «none» | «minimal» | «low» …  (parámetro `reasoning.effort` de OpenRouter)
    prices: dict = field(default_factory=lambda: dict(DEFAULT_PRICES))
    publish_threshold: float = 0.80
    discard_threshold: float = 0.30
    pdf_url_base: str = ""            # si los PDF están publicados en una URL (intranet, SharePoint), los enlaces del informe apuntan ahí


def load_config() -> OpinionConfig:
    s = get_settings()
    o = {}
    if CONFIG_FILE.exists():
        o = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("opinion", {})
    prices = dict(DEFAULT_PRICES)
    prices.update({k: tuple(v) for k, v in o.get("prices", {}).items()})
    return OpinionConfig(model_text=o.get("model_text", s.model_main), model_vision=o.get("model_vision", s.model_vision),
                         reasoning=o.get("reasoning", "none"), prices=prices,
                         publish_threshold=s.publish_threshold, discard_threshold=s.discard_threshold,
                         pdf_url_base=o.get("pdf_url_base", "").rstrip("/"))


class Usage:
    """Tokens y coste acumulados en una ejecución (hilo-seguro: las llamadas van en paralelo)."""

    def __init__(self, cfg: OpinionConfig):
        self.cfg, self.calls, self.prompt, self.completion, self.reasoning, self.cost = cfg, 0, 0, 0, 0, 0.0
        self._lock = threading.Lock()

    def add(self, model: str, usage: dict) -> None:
        p, c = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        r = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)   # van dentro de completion
        pin, pout = self.cfg.prices.get(model, (0.0, 0.0))
        with self._lock:
            self.calls += 1; self.prompt += p; self.completion += c; self.reasoning += r
            self.cost += (p * pin + c * pout) / 1e6

    def summary(self) -> dict:
        return {"llamadas": self.calls, "tokens_entrada": self.prompt, "tokens_salida": self.completion,
                "tokens_razonamiento": self.reasoning, "coste_usd": round(self.cost, 4)}


# Nivel de razonamiento que acepta cada modelo. Algunos (Gemini 3.8 Flash) no permiten «none»: se baja al mínimo que
# acepten y se recuerda, para no repetir el intento fallido en cada llamada.
_REASONING_OK: dict[str, str | None] = {}
_LADDER = ["none", "minimal", "low", None]


def _post(model: str, messages: list[dict], reasoning: str, usage: Usage | None, log) -> str:
    s = get_settings()
    if not s.openrouter_api_key:
        raise RuntimeError("Falta OPENROUTER_API_KEY (ponla en .env o como variable de entorno).")
    start = _REASONING_OK.get(model, reasoning)
    levels = _LADDER[_LADDER.index(start):] if start in _LADDER else [start] + _LADDER[1:]
    for level in levels:
        payload = {"model": model, "temperature": 0, "messages": messages, "response_format": {"type": "json_object"}}
        if level:
            payload["reasoning"] = {"effort": level, "exclude": True}
        r = requests.post(s.llm_url, timeout=240, json=payload, headers={
            "Authorization": f"Bearer {s.openrouter_api_key}", "Content-Type": "application/json", "X-Title": "MIAX B5-T4 · opinion"})
        if r.status_code == 400 and "reasoning" in r.text.lower() and level is not None:
            log(f"  llm {model.split('/')[-1]}: no admite reasoning={level}; se prueba el siguiente nivel")
            continue
        if r.status_code != 200:
            raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:300]}")
        _REASONING_OK[model] = level
        break
    else:
        raise RuntimeError("OpenRouter rechaza todos los niveles de reasoning")
    data = r.json()
    u = data.get("usage", {})
    if usage is not None:
        usage.add(model, u)
    r = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    log(f"  llm {model.split('/')[-1]}: {u.get('prompt_tokens', '?')} → {u.get('completion_tokens', '?')} tokens"
        + (f" ({r} de razonamiento)" if r else ""))
    return data["choices"][0]["message"]["content"]


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


def ask_json(schema: Type[T], system: str, user, model: str, reasoning: str = "none", usage: Usage | None = None,
             images: list[Path] | None = None, log=print) -> T:
    """JSON validado con Pydantic; si no valida, un reintento con el error. `images`: rutas PNG → modelo de visión."""
    content = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": f"data:{mimetypes.guess_type(p.name)[0] or 'image/png'};base64,"
                                                       f"{base64.b64encode(p.read_bytes()).decode()}"}} for p in images]
    msgs = [{"role": "system", "content": system + _schema_hint(schema)}, {"role": "user", "content": content}]
    txt = _post(model, msgs, reasoning, usage, log)
    try:
        return schema.model_validate(_extract_json(txt))
    except (ValidationError, ValueError) as e:
        log(f"  llm: JSON no válido ({str(e)[:120]}), reintento")
        msgs += [{"role": "assistant", "content": txt},
                 {"role": "user", "content": f"Tu respuesta no cumplía el esquema: {str(e)[:800]}\nCorrígela."}]
        return schema.model_validate(_extract_json(_post(model, msgs, reasoning, usage, log)))
