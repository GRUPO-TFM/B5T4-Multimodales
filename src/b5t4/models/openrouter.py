"""OpenRouter multimodal con presupuesto persistente y costes reconciliados por petición."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

import requests

from ..config import get_settings
from .llm import _extract_json, _schema_hint


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5: raise
            time.sleep(.02 * (attempt + 1))


def media_manifest(value, key=""):
    """Conserva prompts exactos y registra medios por hash, sin duplicar base64."""
    if isinstance(value, dict): return {k: media_manifest(v, k) for k, v in value.items()}
    if isinstance(value, list): return [media_manifest(v, key) for v in value]
    if isinstance(value, str) and (value.startswith("data:image/") or key == "data" and len(value)>1000):
        return {"sha256": hashlib.sha256(value.encode()).hexdigest(), "characters": len(value)}
    return value


class BudgetExceeded(RuntimeError):
    pass


class UsageLedger:
    """Una reserva incierta sigue contando: un fallo de red no convierte la llamada en gratis."""
    def __init__(self, path: Path, limit: float, log=print):
        self.path, self.limit, self.log, self.lock = path, limit, log, threading.Lock()
        self.entries = json.loads(path.read_text(encoding="utf-8")).get("entries", []) if path.exists() else []
        self.save()

    @property
    def spent(self):
        return sum(e.get("actual_usd") if e.get("actual_usd") is not None else e["reserved_usd"] for e in self.entries)

    def save(self):
        write_json(self.path, {"limit_usd": self.limit, "accounted_usd": round(self.spent, 6),
                              "uncertain_requests": sum(e.get("actual_usd") is None for e in self.entries),
                              "entries": self.entries})

    def reserve(self, stage: str, model: str, estimate: float) -> int:
        if not math.isfinite(estimate) or estimate <= 0:
            raise ValueError("La estimación debe ser positiva y finita")
        with self.lock:
            if self.spent + estimate > self.limit:
                raise BudgetExceeded(f"Presupuesto: {self.spent:.2f} USD contabilizados; la siguiente llamada "
                                     f"requiere reservar {estimate:.2f} USD y el límite es {self.limit:.2f} USD")
            self.entries.append({"stage": stage, "model": model, "reserved_usd": round(estimate, 6),
                                 "actual_usd": None, "state": "reserved", "at": dt.datetime.now().isoformat()})
            self.save()
            return len(self.entries) - 1

    def settle(self, index: int, generation_id: str, actual: float | None, usage=None, error=""):
        with self.lock:
            entry = self.entries[index]
            if actual is not None and (not math.isfinite(actual) or actual < 0):
                actual = None
            entry.update(generation_id=generation_id, actual_usd=actual, usage=usage or {},
                         state="failed" if error else "complete", error=error[:200])
            self.save()
        self.log(f"  OpenRouter: {self.spent:.3f} / {self.limit:.2f} USD contabilizados")
        if self.spent > self.limit:
            raise BudgetExceeded("El coste comunicado por el proveedor supera el presupuesto; se detienen las llamadas")

    def reconcile(self, reader):
        """Recupera costes pendientes sin volver a generar contenido."""
        for index, entry in enumerate(list(self.entries)):
            if entry.get("actual_usd") is None and entry.get("generation_id"):
                actual = reader(entry["generation_id"])
                if actual is not None:
                    self.settle(index, entry["generation_id"], actual, entry.get("usage"), entry.get("error", ""))


class OpenRouter:
    def __init__(self, out: Path, limit: float = 5, log=print):
        self.settings, self.out, self.log = get_settings(), out, log
        self.base = self.settings.llm_url.removesuffix("/chat/completions")
        self.headers = {"Authorization": "Bearer " + self.settings.openrouter_api_key,
                        "Content-Type": "application/json", "X-Title": "MIAX Onboarding v2"}
        self.ledger = UsageLedger(out / "consumo_openrouter.json", limit, log)
        self.rates = {}

    def catalog(self):
        if not self.rates:
            result = requests.get(self.base + "/models", params={"output_modalities": "all"}, timeout=30)
            result.raise_for_status()
            self.rates = {model["id"]: model for model in result.json()["data"]}
        return self.rates

    def estimate(self, model: str, chars: int, max_output: int = 5000, *, seconds=0, image=False):
        data = self.catalog().get(model)
        if data is None:
            raise ValueError(f"Modelo no disponible en OpenRouter: {model}")
        prices = data["pricing"]
        prompt = float(prices.get("prompt", 0))
        completion = float(prices.get("completion", 0))
        # Audio: 50 tokens/s + margen. Imagen: reserva conservadora por recurso 1K.
        output = max_output if not seconds else math.ceil(seconds * 50) + 1024
        estimate = (math.ceil(chars / 2) * prompt + output * completion) * 1.3
        return max(.50 if image else .002, estimate)

    def generation_cost(self, generation_id):
        for attempt in range(3):
            try:
                response = requests.get(self.base + "/generation", params={"id": generation_id},
                                        headers=self.headers, timeout=20)
                if response.ok:
                    data = response.json().get("data", {})
                    value = data.get("total_cost")
                    if value is not None:
                        return float(value)
            except (requests.RequestException, ValueError, TypeError):
                pass
            if attempt < 2:
                time.sleep(.4 * (attempt + 1))
        return None

    def _request(self, endpoint: str, payload: dict, stage: str, estimate: float, raw=False):
        if not self.settings.has_llm:
            raise RuntimeError("Falta OPENROUTER_API_KEY")
        if self.ledger.spent + estimate > self.ledger.limit:
            self.ledger.reconcile(self.generation_cost)
        index = self.ledger.reserve(stage, payload["model"], estimate)
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.ledger.entries[index]["request_sha256"] = request_hash
        self.ledger.save()
        request_file = self.out / "solicitudes" / f"{index:03d}-{request_hash[:12]}.json"
        record = {"stage": stage, "request_sha256": request_hash, "payload": media_manifest(payload)}
        write_json(request_file, record)
        generation_id = ""
        try:
            response = requests.post(self.base + endpoint, headers=self.headers, json=payload, timeout=240)
            generation_id = response.headers.get("X-Generation-Id", "")
            if not response.ok:
                try:
                    detail = str(response.json().get("error", {}).get("message", ""))[:300]
                except ValueError:
                    detail = ""
                detail = detail.replace(self.settings.openrouter_api_key, "[clave]")
                raise RuntimeError(f"OpenRouter HTTP {response.status_code} en {stage}: {detail}")
            data = {} if raw else response.json()
            record["response"] = {"sha256": hashlib.sha256(response.content).hexdigest(), "bytes": len(response.content)} if raw else media_manifest(data)
            write_json(request_file, record)
            generation_id = response.headers.get("X-Generation-Id", "") if raw else data.get("id", "")
            usage = data.get("usage", {})
            actual = usage.get("cost")
            actual = float(actual) if actual is not None else self.generation_cost(generation_id) if generation_id else None
            self.ledger.settle(index, generation_id, actual, usage)
            return response if raw else data
        except Exception as error:
            if self.ledger.entries[index]["state"] == "reserved":
                self.ledger.settle(index, generation_id, None, error=str(error))
            raise

    def json(self, schema, system: str, prompt: str, *, stage="redacción", validate=None,
             max_output=6000, temperature=.2, parts=None, model=None):
        model = model or self.settings.model_main
        feedback = ""
        # Gemini cuenta pensamiento y respuesta dentro del mismo límite. Reservamos
        # espacio para ambos y acotamos el esfuerzo también en contratos pequeños.
        token_limit = max(4000, max_output + (8000 if max_output > 2400 else 2000))
        for attempt in range(3):
            user = prompt + feedback
            content = [{"type": "text", "text": user}, *(parts or [])] if parts else user
            payload = {"model": model, "temperature": temperature, "max_tokens": token_limit,
                       "reasoning": {"effort": "low"},
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": system + _schema_hint(schema)},
                                    {"role": "user", "content": content}]}
            key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            cached = self.out / "llm_cache" / (key + ".json")
            result = None
            candidate = None
            try:
                if cached.exists():
                    result = schema.model_validate_json(cached.read_text(encoding="utf-8"))
                else:
                    extra = sum(len(part.get("input_audio", {}).get("data", "")) // 10 for part in (parts or []))
                    data = self._request("/chat/completions", payload, stage,
                                         self.estimate(model, len(user) + len(payload["messages"][0]["content"]) + extra, token_limit))
                    choice = data["choices"][0]
                    if choice.get("finish_reason") == "length":
                        token_limit = min(24000, token_limit * 2)
                        raise ValueError("Respuesta truncada: se amplía la reserva de tokens del siguiente intento")
                    text = choice["message"].get("content") or ""
                    if not text.strip():
                        raise ValueError("El modelo devolvió una respuesta vacía")
                    candidate = _extract_json(text)
                    result = schema.model_validate(candidate)
                if validate:
                    validate(result)
                write_json(cached, result)
                return result
            except ValueError as error:
                if attempt == 2:
                    raise
                self.log(f"  {stage}: corrigiendo {str(error)[:220]}")
                feedback = "\nCorrige este error de contrato: " + str(error)
                feedback += ("\nConserva los elementos aptos. Para textos sin respaldo, copia fielmente la "
                             "afirmación citada y conserva sus condiciones y nombres completos. Si una "
                             "relación no se apoya expresamente, usa un mapa sin flechas. No conviertas "
                             "cadencias semanales y mensuales en pasos consecutivos de un proceso.")
                if result:
                    feedback += "\nIntento anterior:\n" + result.model_dump_json()
                elif candidate is not None:
                    feedback += "\nIntento anterior:\n" + json.dumps(candidate, ensure_ascii=False)
        raise RuntimeError("Contrato inválido")

    def vision(self, schema, system, prompt, images: list[Path], **kwargs):
        parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                 base64.b64encode(path.read_bytes()).decode()}} for path in images]
        return self.json(schema, system, prompt, parts=parts, model=self.settings.model_vision, **kwargs)

    def audio_review(self, schema, system, prompt, wav: Path, **kwargs):
        parts = [{"type": "input_audio", "input_audio": {
            "data": base64.b64encode(wav.read_bytes()).decode(), "format": "wav"}}]
        return self.json(schema, system, prompt, parts=parts, model=self.settings.model_vision, **kwargs)

    def speech(self, text: str, style: str, *, seconds: float, stage="voz") -> tuple[bytes, int]:
        model = self.settings.model_tts
        payload = {"model": model, "input": text, "voice": self.settings.voice_v2, "response_format": "pcm",
                   "provider": {"options": {slug: {"speech_metadata": {"style": style}}
                                              for slug in ("google-ai-studio", "google-vertex")}}}
        response = self._request("/audio/speech", payload, stage,
                                 self.estimate(model, len(text), seconds=seconds), raw=True)
        mime = response.headers.get("Content-Type", "")
        if not mime.startswith("audio/pcm") or len(response.content) < 100 or len(response.content) % 2:
            raise ValueError("El servicio de voz no devolvió audio válido")
        rate = re.search(r"(?:rate|sample_rate)=(\d+)", mime)
        channels = re.search(r"channels=(\d+)", mime)
        if channels and int(channels[1]) != 1:
            raise ValueError("Se esperaba voz mono")
        return response.content, int(rate[1]) if rate else 24000

    def image(self, prompt: str, target: Path, stage="ilustración"):
        model = self.settings.model_image
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "modalities": ["image", "text"], "image_config": {"aspect_ratio": "16:9", "image_size": "1K"}}
        data = self._request("/chat/completions", payload, stage, self.estimate(model, len(prompt), image=True))
        images = data["choices"][0]["message"].get("images", [])
        if not images:
            raise ValueError("El modelo no devolvió una ilustración")
        url = images[0]["image_url"]["url"]
        if not url.startswith("data:image/") or ";base64," not in url:
            raise ValueError("Se esperaba una imagen base64 autocontenida")
        blob = base64.b64decode(url.split(",", 1)[1], validate=True)
        from PIL import Image
        import io
        with Image.open(io.BytesIO(blob)) as image:
            image.verify()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        return target
