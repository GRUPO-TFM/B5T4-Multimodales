"""
Configuración única del MVP.

Idea: el código no sabe nada de rutas ni de claves. Todo sale de tres sitios, por orden de prioridad:
  1. variables de entorno (o el fichero `.env` de la raíz del repo, que se carga solo);
  2. `config/b5t4.toml`;
  3. valores por defecto de este módulo.

Así el mismo repo funciona en el PC de cada miembro del equipo, cada uno con su ruta a la carpeta de datos,
y las claves nunca acaban en Git.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Raíz del repo: src/b5t4/config.py → parents[2]
ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "b5t4.toml"

try:  # python-dotenv es dependencia del proyecto, pero el módulo no debe romper si falta
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Settings:
    # --- corpus (la carpeta de la empresa) ---
    data_dir: Path
    manifest: str = "00_MANIFIESTO.csv"
    context_file: str = "00_CONTEXTO.md"
    opinion_dir: str = "03. Vision Corporativa y Servicio/01. Opinion Corporativa"
    # --- LLM (OpenRouter) ---
    openrouter_api_key: str = ""
    llm_url: str = "https://openrouter.ai/api/v1/chat/completions"
    model_main: str = "google/gemini-3.8-flash"
    model_cheap: str = "deepseek/deepseek-v4.1-flash"
    model_vision: str = "google/gemini-3.8-flash"
    temperature: float = 0.0
    # --- verificador (Jev) ---
    jev_api_key: str = ""
    jev_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    publish_threshold: float = 0.80
    discard_threshold: float = 0.30
    # --- vídeo ---
    fps: int = 25
    width: int = 1920
    height: int = 1080
    voice: str = "em_alex"
    speed: float = 1.1
    max_seconds: int = 120
    words_per_second: float = 2.3
    brand: str = "Gestión Discrecional"
    # --- RAG ---
    index_dir: Path = field(default_factory=lambda: ROOT / "index")
    embedding_model: str = "intfloat/multilingual-e5-small"
    chunk_tokens: int = 450
    top_k: int = 8
    # --- rutas del repo ---
    models_dir: Path = field(default_factory=lambda: ROOT / "models")
    out_dir: Path = field(default_factory=lambda: ROOT / "out")
    templates_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "render" / "templates")

    # Rutas derivadas -----------------------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return self.data_dir / self.manifest

    @property
    def opinion_path(self) -> Path:
        return self.data_dir / self.opinion_dir

    @property
    def has_llm(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def has_verifier(self) -> bool:
        return bool(self.jev_api_key)


def _toml() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Lee la configuración una sola vez por proceso."""
    t = _toml()
    c, l, v, vid, r = (t.get(k, {}) for k in ("corpus", "llm", "verifier", "video", "rag"))
    env = os.environ.get
    data_dir = env("B5T4_DATA_DIR") or c.get("data_dir") or str(ROOT / "data" / "sample")
    index_dir = Path(r.get("index_dir", "index"))
    return Settings(
        data_dir=Path(data_dir).expanduser(),
        models_dir=Path(env("B5T4_MODELS_DIR") or ROOT / "models").expanduser(),
        manifest=c.get("manifest", "00_MANIFIESTO.csv"),
        context_file=c.get("context_file", "00_CONTEXTO.md"),
        opinion_dir=c.get("opinion_dir", Settings.opinion_dir),
        openrouter_api_key=env("OPENROUTER_API_KEY", ""),
        llm_url=l.get("url", Settings.llm_url),
        model_main=env("B5T4_MODEL_MAIN") or l.get("model_main", Settings.model_main),
        model_cheap=env("B5T4_MODEL_CHEAP") or l.get("model_cheap", Settings.model_cheap),
        model_vision=env("B5T4_MODEL_VISION") or l.get("model_vision", Settings.model_vision),
        temperature=float(l.get("temperature", 0)),
        jev_api_key=env("JEV_API_KEY") or env("TYPESAFE_API_KEY", ""),
        jev_url=v.get("url", Settings.jev_url),
        jev_model=v.get("model", Settings.jev_model),
        publish_threshold=float(v.get("publish_threshold", 0.80)),
        discard_threshold=float(v.get("discard_threshold", 0.30)),
        fps=int(vid.get("fps", 25)),
        width=int(vid.get("width", 1920)),
        height=int(vid.get("height", 1080)),
        voice=vid.get("voice", "em_alex"),
        speed=float(vid.get("speed", 1.1)),
        max_seconds=int(vid.get("max_seconds", 120)),
        words_per_second=float(vid.get("words_per_second", 2.3)),
        brand=vid.get("brand", "Gestión Discrecional"),
        index_dir=index_dir if index_dir.is_absolute() else ROOT / index_dir,
        embedding_model=r.get("embedding_model", Settings.embedding_model),
        chunk_tokens=int(r.get("chunk_tokens", 450)),
        top_k=int(r.get("top_k", 8)),
    )
