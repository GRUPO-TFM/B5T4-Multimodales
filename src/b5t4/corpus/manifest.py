"""
El manifiesto: el inventario de la carpeta de la empresa.

`00_MANIFIESTO.csv` tiene una fila por fichero con su ruta, carpeta, sección, tipo, estado
(vigente / archivo / duplicado / no copiado), tamaño y md5. Para los agentes es el primer filtro:
antes de leer un solo documento ya saben cuáles son vigentes, de qué sección son y de qué tipo.
Eso es lo que hace barato el retrieval (filtrar por metadatos antes de buscar por similitud).
"""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, get_settings


@dataclass(frozen=True)
class CorpusFile:
    rel: str            # ruta relativa dentro de la carpeta de datos (con «/»)
    origin: str         # ruta en la carpeta original o «(generado para esta copia)»
    folder: str         # carpeta de primer nivel, p. ej. «10. Seccion Alpha»
    section: str        # etiqueta legible, p. ej. «Alpha»
    kind: str           # tipo de documento (maestro, tesis, informe, contexto…)
    ext: str            # extensión en minúsculas
    status: str         # vigente | archivo | duplicado | no copiado…
    size: int
    md5: str
    path: Path          # ruta absoluta en esta máquina

    @property
    def is_current(self) -> bool:
        """Vigente = ni archivo, ni duplicado, ni ausente. Es lo único que debería leer un agente por defecto."""
        return self.status == "vigente"

    @property
    def is_context(self) -> bool:
        return self.kind == "Documento de contexto de la copia"


def load_manifest(settings: Settings | None = None) -> list[CorpusFile]:
    """Lee el manifiesto. Falla con un mensaje claro si la carpeta de datos no está donde dice la configuración."""
    s = settings or get_settings()
    if not s.manifest_path.exists():
        raise FileNotFoundError(
            f"No encuentro el manifiesto en {s.manifest_path}. "
            "Revisa B5T4_DATA_DIR en .env o data_dir en config/b5t4.toml."
        )
    out: list[CorpusFile] = []
    with open(s.manifest_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out.append(CorpusFile(
                rel=r["destino"], origin=r["origen"], folder=r["carpeta"], section=r["seccion"],
                kind=r["tipo"], ext=r["extension"], status=r["estado"], size=int(r["tamano_bytes"] or 0),
                md5=r["md5"], path=s.data_dir / r["destino"],
            ))
    return out


def select(files: list[CorpusFile], *, current_only: bool = True, folders: tuple[str, ...] | None = None,
           exts: tuple[str, ...] | None = None, kinds: tuple[str, ...] | None = None) -> list[CorpusFile]:
    """Filtro por metadatos: el «pre-router» barato que va antes de cualquier búsqueda semántica."""
    sel = files
    if current_only:
        sel = [f for f in sel if f.is_current]
    if folders:
        sel = [f for f in sel if f.folder.startswith(folders)]
    if exts:
        sel = [f for f in sel if f.ext in exts]
    if kinds:
        sel = [f for f in sel if f.kind in kinds]
    return sel


def summary(files: list[CorpusFile]) -> dict:
    """Resumen para `b5t4 check` y para el notebook de exploración."""
    return {
        "ficheros": len(files),
        "vigentes": sum(f.is_current for f in files),
        "contextos": sum(f.is_context for f in files),
        "por_estado": dict(Counter(f.status for f in files).most_common()),
        "por_carpeta": dict(sorted(Counter(f.folder for f in files).items())),
        "por_extension": dict(Counter(f.ext for f in files).most_common(10)),
        "faltan_en_disco": [f.rel for f in files if f.status == "vigente" and not f.path.exists()][:20],
    }
