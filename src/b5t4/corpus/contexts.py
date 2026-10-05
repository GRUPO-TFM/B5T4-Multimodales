"""
Los documentos de contexto: la «columna vertebral» del corpus.

Cada carpeta de la copia tiene un `00_CONTEXTO.md` con la MISMA plantilla:
  1 Qué es · 2 Responsables · 3 Objetivos · 4 Entregables y cadencia · 5 Procesos · 6 Tipos de archivo
  7 Dónde está cada cosa · 8 Reglas · 9 Incoherencias y pendientes · 10 Preguntas frecuentes · 11 Fuentes
más una cabecera YAML con metadatos (sección, responsables, índice Bloomberg…).

Por qué importa para los tres agentes:
  - Onboarding: el guion sale de las secciones 1-5 de cada contexto (quién, qué, para qué, cómo).
  - Opinión corporativa: el contexto de `03.` ya trae el índice de ediciones y la tabla de evolución.
  - RAG: trocear por sección (y no por número de caracteres) da fragmentos con sentido completo y
    etiquetados igual en todas las carpetas: «§2 Responsables» de Alpha y de IG se recuperan igual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import Settings, get_settings

_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
_H2 = re.compile(r"(?m)^## (.+)$")


@dataclass
class ContextSection:
    number: str            # «1», «2»… o «Anexo» para los anexos literales
    title: str             # «Qué es», «Responsables»…
    text: str              # cuerpo de la sección (markdown)
    doc_rel: str           # ruta relativa del documento de contexto
    folder: str            # carpeta a la que describe

    @property
    def label(self) -> str:
        return f"{self.folder} · §{self.number} {self.title}"


@dataclass
class ContextDoc:
    rel: str
    path: Path
    meta: dict
    title: str
    intro: str                                   # texto entre el título y la primera sección
    sections: list[ContextSection] = field(default_factory=list)

    def section(self, number: str) -> ContextSection | None:
        return next((s for s in self.sections if s.number == number), None)


def parse_context(path: Path, rel: str) -> ContextDoc:
    """Separa cabecera YAML, título, introducción y secciones `## N. Título`."""
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    m = _FRONT.match(raw)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = raw[m.end():]
    title_m = re.search(r"(?m)^# (.+)$", body)
    title = title_m.group(1).strip() if title_m else rel
    folder = rel.rsplit("/", 1)[0] if "/" in rel else "(raíz)"
    heads = list(_H2.finditer(body))
    intro = body[title_m.end() if title_m else 0: heads[0].start() if heads else len(body)].strip()
    doc = ContextDoc(rel=rel, path=path, meta=meta, title=title, intro=intro)
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        head = h.group(1).strip()
        num_m = re.match(r"(\d+)\.\s*(.+)", head)
        number, sec_title = (num_m.group(1), num_m.group(2)) if num_m else ("Anexo", head)
        doc.sections.append(ContextSection(number=number, title=sec_title,
                                           text=body[h.end(): end].strip().rstrip("-").strip(),
                                           doc_rel=rel, folder=folder))
    return doc


def load_contexts(settings: Settings | None = None) -> list[ContextDoc]:
    """Todos los `00_CONTEXTO.md` de la carpeta de datos, ordenados por ruta (la raíz primero)."""
    s = settings or get_settings()
    docs = []
    for p in sorted(s.data_dir.rglob(s.context_file), key=lambda p: (len(p.relative_to(s.data_dir).parts), str(p))):
        rel = p.relative_to(s.data_dir).as_posix()
        docs.append(parse_context(p, rel))
    return docs


def section_index(docs: list[ContextDoc]) -> dict[str, list[ContextSection]]:
    """Vista transversal: para cada número de sección, esa sección en todas las carpetas.
    Ejemplo: section_index(docs)["2"] → los «Responsables» de todas las carpetas."""
    idx: dict[str, list[ContextSection]] = {}
    for d in docs:
        for sec in d.sections:
            idx.setdefault(sec.number, []).append(sec)
    return idx
