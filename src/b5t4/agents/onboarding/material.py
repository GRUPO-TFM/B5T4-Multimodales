"""Lectura acotada del corpus y resolución de referencias, sin ejecutar sus instrucciones."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ...config import Settings, get_settings
from ...corpus import extract, load_contexts, load_manifest
from ...corpus.extract import SUPPORTED
from ...corpus.manifest import CorpusFile
from .schemas import Evidence, OutlineBlock


def _norm(value: str) -> str:
    return value.replace("\\", "/").strip().strip("`\"'").casefold()


def split_text(text: str, limit: int = 5500) -> list[str]:
    """Conserva todo el texto, con fragmentos acotados para el verificador."""
    chunks, current = [], ""
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        while len(paragraph) > limit:
            cut = paragraph.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if current:
                chunks.append(current); current = ""
            chunks.append(paragraph[:cut]); paragraph = paragraph[cut:].lstrip()
        if current and len(current) + len(paragraph) + 2 > limit:
            chunks.append(current); current = ""
        current = (current + "\n\n" + paragraph).strip()
    if current:
        chunks.append(current)
    return chunks


@dataclass
class Material:
    settings: Settings
    files: list[CorpusFile]
    evidence: dict[str, Evidence] = field(default_factory=dict)
    contexts: dict[str, dict] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)

    def resolve(self, reference: str, context: str = "") -> CorpusFile | None:
        """Resuelve ruta de copia, ruta de origen y nombre único; nunca elige entre ambiguos."""
        # Las referencias pueden terminar en una versión, un apartado o un ancla.
        match = re.search(r"(.+?\.(?:md|txt|csv|json|html?|eml|pdf|pptx|xlsx))(?:$|[\s#])", reference, re.I)
        ref = _norm(match.group(1) if match else reference)
        root = _norm(str(self.settings.data_dir)).rstrip("/") + "/"
        if ref.startswith(root):
            ref = ref[len(root):]
        candidates = {ref}
        if context and not re.match(r"^[a-z]:/", ref):
            parent = PurePosixPath(context).parent
            joined = self.settings.data_dir / parent / ref
            try:
                rel = joined.resolve().relative_to(self.settings.data_dir.resolve()).as_posix()
                candidates.add(_norm(rel))
            except ValueError:
                self.issues.append({"reference": reference, "context": context, "reason": "ruta fuera del corpus"})
                return None
        exact = [f for f in self.files if _norm(f.rel) in candidates or _norm(f.origin) in candidates]
        if not exact:
            exact = [f for f in self.files if _norm(f.origin).endswith("/" + ref)]
        if not exact and "/" not in ref:
            exact = [f for f in self.files if _norm(Path(f.rel).name) == ref]
        current = [f for f in exact if f.is_current]
        if len(current) == 1:
            return current[0]
        reason = "referencia ambigua" if len(current) > 1 else ("documento no vigente" if exact else "referencia no localizada")
        self.issues.append({"reference": reference, "context": context, "reason": reason})
        return None

    def read_document(self, reference: str, context: str = "") -> list[Evidence]:
        file = self.resolve(reference, context)
        if file is None:
            return []
        existing = [e for e in self.evidence.values() if e.source == file.rel]
        if existing:
            return existing
        try:
            path = file.path.resolve()
            path.relative_to(self.settings.data_dir.resolve())
            if file.ext not in SUPPORTED:
                raise ValueError(f"formato no soportado: {file.ext}")
            if not path.is_file():
                raise ValueError("archivo ausente")
            self.hashes[file.rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            pages = extract(path, file.rel)
            if not any(p.text.strip() for p in pages):
                raise ValueError("sin texto extraíble; requiere revisión visual")
        except Exception as exc:
            self.issues.append({"reference": file.rel, "reason": str(exc)[:250]})
            return []
        self.reads.append(file.rel)
        records = []
        prefix = hashlib.sha256(file.rel.encode()).hexdigest()[:10]
        for page in pages:
            for n, text in enumerate(split_text(page.text), 1):
                record = Evidence(id=f"D-{prefix}-{page.page}-{n}", source=file.rel,
                                  page=page.page, heading=f"p. {page.page} · fragmento {n}", text=text, kind="document")
                records.append(record); self.evidence[record.id] = record
        return records

    def catalog(self) -> list[dict]:
        # Los archivos de ejecuciones y modelos de inversión no son documentación de incorporación.
        return [{"path": f.rel, "kind": f.kind} for f in self.files if f.is_current
                and f.ext in SUPPORTED and f.ext not in (".json", ".csv")
                and f.rel not in self.contexts
                and not f.folder.startswith("60. Proyectos")
                and (f.folder.startswith(("01.", "02.", "03.", "04.", "05."))
                     or re.search(r"readme|instrucciones|marco|glosario|personas|calendario|operativa|reglas|claude|leeme", f.rel, re.I))]

    def for_block(self, block: OutlineBlock) -> list[Evidence]:
        records = [e for e in self.evidence.values() if e.kind == "context" and e.source in block.sources
                   and e.section in block.sections]
        for rel in block.document_paths:
            records.extend(self.read_document(rel))
        return list({e.id: e for e in records}.values())

    def planning_text(self) -> str:
        summaries = []
        for path, meta in self.contexts.items():
            # Extractos para orientarse; la redacción recibe después los apartados íntegros.
            fragments = [{"section": e.section, "heading": e.heading, "preview": e.text[:900]}
                         for e in self.evidence.values() if e.source == path and e.section in ("1", "2", "4", "7", "8", "9")]
            summaries.append({"path": path, "title": meta["title"], "references": meta["references"], "sections": fragments})
        return json.dumps({"contexts": summaries, "documents": self.catalog()}, ensure_ascii=False)

    def dossier(self) -> str:
        return "\n\n---\n\n".join(f"## [{e.id}] {e.source}\n### {e.heading}\n\n{e.text}" for e in self.evidence.values())

    def save(self, out: Path) -> None:
        (out / "dosier.md").write_text(self.dossier(), encoding="utf-8")
        payload = {"data_dir": str(self.settings.data_dir), "contexts": self.contexts,
                   "documents_read": self.reads, "issues": self.issues, "sha256": self.hashes,
                   "evidence": [e.model_dump() for e in self.evidence.values()]}
        (out / "fuentes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def collect_material(settings: Settings | None = None) -> Material:
    s = settings or get_settings()
    material = Material(s, load_manifest(s))
    docs = load_contexts(s)
    if not docs:
        raise ValueError(f"No hay documentos de contexto en {s.data_dir}")
    for n, doc in enumerate(docs, 1):
        refs = doc.meta.get("fuentes", [])
        refs = refs if isinstance(refs, list) else [str(refs)]
        material.contexts[doc.rel] = {"title": doc.title, "references": refs, "metadata": doc.meta}
        material.hashes[doc.rel] = hashlib.sha256(doc.path.read_bytes()).hexdigest()
        for section_index, sec in enumerate(doc.sections):
            for k, text in enumerate(split_text(sec.text), 1):
                part = sec.number if sec.number != "Anexo" else f"Anexo{section_index}"
                eid = f"C{n:02d}-{part}-{k}"
                material.evidence[eid] = Evidence(id=eid, source=doc.rel, heading=f"§{sec.number} {sec.title}",
                                                 section=sec.number, text=text)
    return material
