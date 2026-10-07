"""Regresiones de fuentes, publicación y duración; no necesitan datos privados ni APIs."""
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from b5t4.agents.onboarding import pipeline
from b5t4.agents.onboarding.material import Material, collect_material, split_text
from b5t4.agents.onboarding.schemas import (BlockDraft, Evidence, Fact, InfographicPlan,
                                          OutlineBlock, ReportBlock, VerifiedFact, VerifiedReport)
from b5t4.config import Settings
from b5t4.corpus.manifest import CorpusFile
from b5t4.render import video
from b5t4.render.report import md_to_html
from b5t4.render.schemas import Scene, Storyboard


def corpus_file(root, rel, origin="old/file.md", status="vigente"):
    return CorpusFile(rel, origin, rel.split("/")[0], "equipo", "manual", Path(rel).suffix, status, 1, "", root / rel)


def test_references_use_origin_and_refuse_ambiguous_or_archived(tmp_path):
    files = [corpus_file(tmp_path, "nuevo/a.md", "C:/original/manual.md"),
             corpus_file(tmp_path, "nuevo/old.md", status="archivo"),
             corpus_file(tmp_path, "uno/igual.md"), corpus_file(tmp_path, "dos/igual.md")]
    m = Material(Settings(data_dir=tmp_path), files)
    assert m.resolve("C:\\original\\manual.md v1.1").rel == "nuevo/a.md"
    assert m.resolve("../nuevo/a.md", "otra/00_CONTEXTO.md").rel == "nuevo/a.md"
    assert m.resolve("igual.md") is None
    assert m.resolve("nuevo/old.md") is None
    assert m.resolve("../../fuera.md", "00_CONTEXTO.md") is None
    assert {issue["reason"] for issue in m.issues} >= {"referencia ambigua", "documento no vigente", "ruta fuera del corpus"}


def test_reader_blocks_manifest_escape_and_unsupported_formats(tmp_path):
    # No lectura: la ruta queda fuera de la raíz aunque el manifiesto la anunciase vigente.
    m = Material(Settings(data_dir=tmp_path), [corpus_file(tmp_path, "../outside-private.md"),
                                             corpus_file(tmp_path, "datos.xlsx")])
    assert m.read_document("../outside-private.md") == []
    assert m.read_document("datos.xlsx") == []
    assert m.reads == []


def test_contexts_keep_rules_sources_annexes_and_date_metadata(tmp_path):
    context = tmp_path / "00_CONTEXTO.md"
    context.write_text("---\nfecha_copia: 2026-10-05\n---\n# Equipo\n" +
                       "\n".join(f"## {n}. Apartado\nContenido del apartado {n}." for n in range(1, 12)) +
                       "\n## Anexo uno\nPrimera nota.\n## Anexo dos\nSegunda nota.", encoding="utf-8")
    fields = ["destino", "origen", "carpeta", "seccion", "tipo", "extension", "estado", "tamano_bytes", "md5"]
    with (tmp_path / "00_MANIFIESTO.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        writer.writerow(dict(zip(fields, [context.name, "generated", "root", "equipo", "contexto", ".md", "vigente", "1", ""])))
    m = collect_material(Settings(data_dir=tmp_path))
    assert len(m.evidence) == 13
    assert {"7", "8", "9", "11"} <= {e.section for e in m.evidence.values()}
    out = tmp_path / "out"; out.mkdir(); m.save(out)
    assert json.loads((out / "fuentes.json").read_text(encoding="utf-8"))["contexts"][context.name]["metadata"]["fecha_copia"] == "2026-10-05"


def test_long_evidence_is_split_without_losing_words():
    text = " ".join(f"palabra{i}" for i in range(3000))
    chunks = split_text(text, 1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_document_evidence_retains_path_and_is_read_once(tmp_path):
    (tmp_path / "manual.md").write_text("Cada lunes se entrega el informe semanal.", encoding="utf-8")
    m = Material(Settings(data_dir=tmp_path), [corpus_file(tmp_path, "manual.md")])
    first = m.read_document("manual.md")
    assert first == m.read_document("manual.md")
    assert first[0].source == "manual.md"
    assert first[0].page == 1
    assert m.reads == ["manual.md"]


def test_unknown_citations_are_rejected():
    evidence = [Evidence(id="real", source="manual.md", heading="Reglas", text="Regla")]
    with pytest.raises(ValueError, match="desconocidos"):
        pipeline.validate_draft(Fact(text="Esta afirmación cita una fuente inventada.", source_ids=["inventada"]), evidence)


def test_report_excludes_unverified_claims_and_keeps_source_locations(tmp_path):
    m = Material(Settings(data_dir=tmp_path), [])
    m.evidence["E1"] = Evidence(id="E1", source="reglas.md", heading="§8 Reglas", text="Los lunes se entrega el informe.")
    report = VerifiedReport(title="Bienvenida al equipo", audience="nuevo empleado", blocks=[
        ReportBlock(id="calendar", title="Calendario", facts=[
            VerifiedFact(id="ok", text="Los lunes se entrega el informe.", source_ids=["E1"], status="publicar", probability=.99),
            VerifiedFact(id="bad", text="Se entrega también en Marte.", source_ids=["E1"], status="descartar", probability=.01)])])
    md = pipeline.report_markdown(report, m)
    assert "Marte" not in md
    assert "reglas.md" in md and "§8 Reglas" in md
    assert "[ok; E1]" in md


def test_visuals_cannot_cite_discarded_claims(tmp_path):
    report = VerifiedReport(title="Equipo", audience="empleado", blocks=[])
    plan = InfographicPlan(blocks=[{"kind": kind, "title": "Panel de equipo", "items": [
        {"label": "Equipo", "detail": "Detalle del equipo", "claim_ids": ["inventada"]},
        {"label": "Trabajo", "detail": "Detalle del trabajo", "claim_ids": ["inventada"]}]} for kind in ("orgchart", "people", "flow", "timeline")])
    with pytest.raises(ValueError, match="no publicadas"):
        pipeline.validate_visuals(plan, report, pipeline.SupportChecks(tmp_path / "checks.json"))


def test_resume_refuses_changed_documents(tmp_path):
    root = tmp_path / "data"; root.mkdir()
    doc = root / "manual.md"; doc.write_text("Texto cambiado", encoding="utf-8")
    m = Material(Settings(data_dir=root), [])
    out = tmp_path / "run"; out.mkdir()
    (out / "ejecucion.json").write_text(json.dumps({"inputs": {"version": 1}}))
    (out / "fuentes.json").write_text(json.dumps({"sha256": {"manual.md": "old"}, "documents_read": []}))
    with pytest.raises(ValueError, match="Ha cambiado"):
        pipeline._validate_resume(out, {"version": 1}, m)


def test_narration_uses_measured_audio_and_reuses_unchanged_clips(tmp_path, monkeypatch):
    calls = []
    def synthesize(text, **kw):
        calls.append(text)
        return np.ones(24000 * 4, dtype=np.float32) * .1, 24000
    monkeypatch.setattr(video.tts, "synthesize", synthesize)
    monkeypatch.setattr(video.tts, "verbalize", lambda text: text)
    monkeypatch.setattr(video, "get_settings", lambda: Settings(data_dir=tmp_path))
    sb = Storyboard(topic="Equipo", scenes=[Scene(id="s1", kind="title", narration="Bienvenido al equipo")])
    tl = video.narrate(sb, tmp_path, log=lambda _: None)
    assert tl["total"] == pytest.approx(4.8)
    assert tl["scenes"][0]["voice_seconds"] == 4
    video.narrate(sb, tmp_path, log=lambda _: None)
    assert calls == ["Bienvenido al equipo"]


def test_templates_receive_escaped_report_text():
    html = md_to_html("# <script>alert('x')</script>\n\n**Nombre** & equipo")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "<strong>Nombre</strong>" in html


def test_invalid_onboarding_scene_is_rejected():
    with pytest.raises(ValueError, match="tarjeta"):
        Scene(id="scene", kind="flow", narration="Proceso", data={"title": "Un proceso", "items": [{"label": "Sin detalle"}]})


def test_ui_surfaces_partial_outputs_when_generation_fails(tmp_path, monkeypatch):
    from b5t4.agents import onboarding
    from b5t4.app.ui import _onboarding
    (tmp_path / "informe.md").write_text("# Borrador", encoding="utf-8")
    def fail(**kwargs):
        kwargs["log"](f"Salida: {tmp_path}")
        raise ValueError("Servicio temporalmente indisponible")
    monkeypatch.setattr(onboarding, "run", fail)
    results = list(_onboarding())
    status, report, image, movie, files = results[-1]
    assert "No se ha completado" in status and "reanudar" in status
    assert report == "# Borrador" and str(tmp_path / "informe.md") in files
    assert image is None and movie is None


@pytest.mark.parametrize("rechecked, expected", [(.91, "publicar"), (.4, "revisar")])
def test_repaired_claim_is_checked_again_before_publication(rechecked, expected, monkeypatch):
    evidence = [Evidence(id="E1", source="calendario.md", heading="Calendario",
                         text="El informe semanal se entrega los lunes.")]
    block = OutlineBlock(id="calendar", title="Calendario", key_points=["Cadencia", "Entrega"],
                         sources=["00_CONTEXTO.md"], sections=["1"])
    draft = BlockDraft(facts=[Fact(text=f"Afirmación original número {n}.", source_ids=["E1"])
                             for n in range(3)])
    repaired = Fact(text="El informe semanal se entrega los lunes.", source_ids=["E1"])
    repairs, checks = [], []

    def repair(fact, sources, log):
        repairs.append(fact.text)
        return repaired

    class Checks:
        def many(self, pairs):
            return [.95, .5, .95]

        def check(self, claim, passage):
            checks.append((claim, passage))
            return rechecked

    monkeypatch.setattr(pipeline, "repair_fact", repair)
    result = pipeline.verify_block(block, draft, evidence, Checks(), log=lambda _: None)
    assert repairs == [draft.facts[1].text]
    assert checks == [(repaired.text, "[E1] Calendario\n" + evidence[0].text)]
    assert result.facts[1].status == expected
    assert result.facts[1].corrections == 1
    assert result.facts[0].corrections == result.facts[2].corrections == 0


def test_visuals_reject_unsupported_hierarchy_even_when_cards_are_supported():
    report = VerifiedReport(title="Equipo", audience="empleado", blocks=[
        ReportBlock(id="people", title="Personas", facts=[
            VerifiedFact(id="people-01", text="Ana y Luis trabajan en el equipo.", source_ids=["E1"],
                         status="publicar", probability=.99)])])
    plan = InfographicPlan(blocks=[{"kind": kind, "title": "Panel de equipo", "items": [
        {"label": name, "detail": "Trabaja en el equipo", "claim_ids": ["people-01"]}
        for name in ("Ana", "Luis")]} for kind in ("orgchart", "people", "flow", "timeline")])

    class Checks:
        def many(self, pairs):
            return [.2 if claim.startswith("Jerarquía") else .99 for claim, _ in pairs]

    with pytest.raises(ValueError, match="relación entre tarjetas del bloque 1"):
        pipeline.validate_visuals(plan, report, Checks())


def test_ui_opens_saved_outputs_without_running_generation(tmp_path):
    from b5t4.app.ui import _load_onboarding
    (tmp_path / "ejecucion.json").write_text(json.dumps({"status": "complete", "stage": "Completado"}))
    (tmp_path / "informe.md").write_text("# Informe guardado", encoding="utf-8")
    (tmp_path / "infografia.png").write_bytes(b"saved image")
    (tmp_path / "video.mp4").write_bytes(b"saved video")
    status, report, image, movie, files = _load_onboarding(str(tmp_path))
    assert "Onboarding completo" in status and report == "# Informe guardado"
    assert image == str(tmp_path / "infografia.png") and movie == str(tmp_path / "video.mp4")
    assert len(files) == 4
