"""Eficiencia del onboarding v2 (8-oct-2026): capítulos en paralelo, fotogramas en varios navegadores,
reparación de párrafos sin regenerar el capítulo y Jev por lotes. Sin claves ni datos: todo con dobles."""
import json
import threading
import time

import numpy as np
import pytest
from PIL import Image

from b5t4.agents.onboarding.v2_content import Checks, repair_paragraphs, write_chapter
from b5t4.agents.onboarding.v2_pipeline import StageArtifacts, parallel
from b5t4.agents.onboarding.v2_schemas import CitedText, FactBank, FactChapter, GuideChapter
from b5t4.agents.onboarding.schemas import VerifiedFact
from b5t4.models import verifier


@pytest.fixture
def bank():
    return FactBank(title="Guía del equipo", chapters=[FactChapter(id="team", title="Equipo", purpose="Conocer el equipo", common=True,
        facts=[VerifiedFact(id="team-01", text="Ana y Luis trabajan en el equipo.", source_ids=["E1"], probability=.99, status="publicar"),
               VerifiedFact(id="team-02", text="Se abre el maestro antes de validar el control.", source_ids=["E2"], probability=.99, status="publicar")])])


# ------------------------------------------------------------------ D · Jev por lotes
def test_claims_sharing_a_passage_travel_in_one_request_and_keep_per_claim_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(Checks, "BATCH", 5)                  # el mecanismo de lotes (desactivado por defecto)
    requests = []
    def ask(state, questions):
        requests.append((state, questions))
        return {key: {"noul": .9 if "Luis" in state.split(f"AFIRMACIÓN {key[1:]}:")[1].split("\n")[1] else .3} for key in questions}
    monkeypatch.setattr(verifier, "available", lambda: True)
    monkeypatch.setattr(verifier, "_ask", ask)
    monkeypatch.setattr(verifier, "supports", lambda claim, passage: requests.append(("single", claim)) or .5)
    checks = Checks(tmp_path / "run", tmp_path / "shared.json", lambda _: None)
    pairs = [("Ana dirige a Luis.", "P1"), ("Luis trabaja con Ana.", "P1"), ("Ana dirige a Luis.", "P1"),
             ("El maestro se abre el lunes.", "P2")] + [(f"Afirmación {i} sobre Luis.", "P3") for i in range(7)]
    values = checks.many(pairs)
    assert values[0] == values[2] == .9 and values[1] == .9 and values[3] == .5           # orden conservado; repetida pedida una vez
    assert sum(1 for r in requests if r[0] != "single") == 3                               # P1 (1 lote), P3 (5 + 2)
    assert sum(1 for r in requests if r[0] == "single") == 1                               # P2: una sola afirmación → supports
    assert checks.stats["requests"] == 4
    requests.clear()
    assert checks.many(pairs) == values and not requests                                   # todo en caché, por afirmación
    assert checks.check("Luis trabaja con Ana.", "P1") == .9 and not requests
    assert (tmp_path / "run" / "consumo_jev.json").exists()                                 # estadísticas guardadas al cerrar el lote


def test_batch_results_are_shared_with_single_checks_and_other_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(Checks, "BATCH", 5)
    monkeypatch.setattr(verifier, "available", lambda: True)
    monkeypatch.setattr(verifier, "_ask", lambda state, questions: {k: {"noul": .95} for k in questions})
    monkeypatch.setattr(verifier, "supports", lambda *a: pytest.fail("no debería hacer falta"))
    first = Checks(tmp_path / "one", tmp_path / "shared.json", lambda _: None)
    first.many([("a", "P"), ("b", "P")])
    second = Checks(tmp_path / "two", tmp_path / "shared.json", lambda _: None)
    assert second.check("b", "P") == .95 and second.stats["cache_hits"] == 1 and second.stats["requests"] == 0


# ------------------------------------------------------------------ C · párrafo flojo → reparación acotada
class Gate:
    log = staticmethod(lambda _: None)
    def __init__(self, tmp_path): self.out = tmp_path
    def many(self, pairs): return [.2 if "dirige" in claim else .99 for claim, _ in pairs]
    def check(self, claim, passage): return self.many([(claim, passage)])[0]
    def require(self, pairs, labels):
        bad = [label for label, value in zip(labels, self.many(pairs)) if value < .8]
        if bad: raise ValueError("Respaldo insuficiente: " + "; ".join(bad))


def chapter(weak_text):
    return GuideChapter(id="team", title="Equipo", paragraphs=[
        {"text": "Ana y Luis trabajan en el equipo.", "claim_ids": ["team-01"]},
        {"text": weak_text, "claim_ids": ["team-01"]},
        {"text": "Se abre el maestro antes de validar el control.", "claim_ids": ["team-02"]}])


def test_weak_paragraph_is_rewritten_in_place_and_the_rest_is_untouched(tmp_path, bank):
    class Client:
        calls = []
        def json(self, schema, system, prompt, *, validate=None, **kwargs):
            self.calls.append(schema.__name__)
            value = CitedText(text="Ana y Luis trabajan en el equipo de gestión.", claim_ids=["team-01"])
            if validate: validate(value)
            return value
    result = chapter("Ana dirige a Luis.")
    repair_paragraphs(result, bank, Client(), Gate(tmp_path))
    assert Client.calls == ["CitedText"] and "trabajan" in result.paragraphs[1].text
    assert result.paragraphs[0].text == "Ana y Luis trabajan en el equipo." and len(result.paragraphs) == 3
    assert json.loads((tmp_path / "ajustes_parrafos.json").read_text(encoding="utf-8"))[0]["paragraph"] == 2


def test_chapter_is_requested_once_even_when_a_paragraph_needs_repair(tmp_path, bank):
    """Antes, un párrafo flojo hacía fallar el contrato y el capítulo entero se pedía de nuevo (3 intentos)."""
    class Client:
        def __init__(self): self.chapters, self.repairs = 0, 0
        def json(self, schema, system, prompt, *, validate=None, **kwargs):
            if schema is GuideChapter:
                self.chapters += 1
                value = chapter("Ana dirige a Luis.")
            else:
                self.repairs += 1
                value = CitedText(text="Ana y Luis trabajan en el equipo de gestión.", claim_ids=["team-01"])
            if validate: validate(value)
            return value
    client = Client()
    brief = type("Brief", (), {"model_dump_json": lambda self: "{}"})()
    result = write_chapter(bank.chapters[0], brief, bank, client, Gate(tmp_path))
    assert client.chapters == 1 and client.repairs == 1 and "trabajan" in result.paragraphs[1].text


def test_repair_gives_up_after_two_rounds_so_the_contract_can_still_fail(tmp_path, bank):
    class StubbornClient:
        calls = 0
        def json(self, schema, system, prompt, *, validate=None, **kwargs):
            self.calls += 1
            return CitedText(text="Ana dirige a Luis otra vez.", claim_ids=["team-01"])
    client = StubbornClient()
    with pytest.raises(ValueError, match="tras la reparación"):
        repair_paragraphs(chapter("Ana dirige a Luis."), bank, client, Gate(tmp_path))
    assert client.calls == 2


# ------------------------------------------------------------------ A · capítulos en paralelo
def test_parallel_keeps_order_and_propagates_errors():
    def slow(item):
        time.sleep(.05 * (4 - item))
        return item * 10
    started = time.perf_counter()
    assert parallel(slow, [1, 2, 3], 3) == [10, 20, 30]
    assert time.perf_counter() - started < .3                                             # los tres a la vez, no en serie
    assert parallel(slow, [1, 2, 3], 1) == [10, 20, 30]
    def boom(item):
        if item == 2: raise ValueError("capítulo 2")
        return item
    with pytest.raises(ValueError, match="capítulo 2"):
        parallel(boom, [1, 2, 3], 3)


def test_stage_artifacts_survive_concurrent_contracts(tmp_path):
    artifacts = StageArtifacts(tmp_path, None, "recipe")
    def build(index):
        return artifacts.get(f"referencia_{index}.json", CitedText,
                             lambda: CitedText(text=f"capítulo {index} con texto", claim_ids=[f"c-{index}"]),
                             dependencies=[index])
    results = parallel(build, range(8), 8)
    assert [r.claim_ids for r in results] == [[f"c-{i}"] for i in range(8)]
    saved = json.loads((tmp_path / "etapas.json").read_text(encoding="utf-8"))
    assert sorted(saved) == sorted(f"referencia_{i}.json" for i in range(8))
    assert all((tmp_path / f"referencia_{i}.json").exists() for i in range(8))


def test_personalized_material_serialises_reads_and_blocks(monkeypatch):
    from b5t4.agents.onboarding import v2_content
    m = v2_content.PersonalizedMaterial.__new__(v2_content.PersonalizedMaterial)
    m._lock = threading.RLock()
    monkeypatch.setattr(v2_content.Material, "for_block", lambda self, block: ["ok"], raising=False)
    assert m.for_block(None) == ["ok"] and isinstance(m._lock, type(threading.RLock()))


# ------------------------------------------------------------------ B · fotogramas en varios navegadores
def test_parallel_capture_produces_the_same_frames_as_a_single_browser(tmp_path, monkeypatch):
    import soundfile as sf
    from b5t4.config import get_settings
    from b5t4.render import video
    from b5t4.render.schemas import Scene, Storyboard

    sb = Storyboard(topic="t", scenes=[Scene(id="uno", kind="title", narration="Uno", data={"title": "Primera escena"}),
                                       Scene(id="dos", kind="title", narration="Dos", data={"title": "Segunda escena"})])
    tl = {"total": 1.0, "scenes": [{"id": "uno", "kind": "title", "start": 0, "duration": .5},
                                   {"id": "dos", "kind": "title", "start": .5, "duration": .5}]}
    digests = {}
    for workers in (1, 3):
        out = tmp_path / f"w{workers}"
        out.mkdir()
        sf.write(out / "voz.wav", np.zeros(24000, np.float32), 24000)
        settings = get_settings().__class__(**{**get_settings().__dict__, "render_workers": workers})   # Settings es inmutable
        monkeypatch.setattr(video, "get_settings", lambda: settings)
        captured = {}
        real = video._capture
        def spy(html, span, s, frames, log, n, real=real, captured=captured):
            captured[span] = threading.get_ident()
            real(html, span, s, frames, log, n)
            for path in frames.glob("f_*.jpg"):
                digests.setdefault(workers, {})[path.name] = np.asarray(Image.open(path).convert("L"), dtype=np.int16)
        monkeypatch.setattr(video, "_capture", spy)
        mp4 = video.render(sb, tl, out, log=lambda _: None)
        assert mp4.exists() and video.inspect_video(mp4)["decoded"]
        assert len(captured) == workers
    assert set(digests[1]) == set(digests[3]) and len(digests[1]) == 25
    # Mismo dibujo en cada instante: la única diferencia admisible es el ruido de rasterizado (≤ 8 niveles de 255)
    worst = max(int(np.abs(digests[1][k] - digests[3][k]).max()) for k in digests[1])
    assert worst <= 8, f"un fotograma difiere hasta {worst} niveles entre 1 y 3 navegadores"


# ------------------------------------------------------------------ frases: no partir «10. Seccion Alpha»
def test_folder_names_with_numeric_prefix_do_not_split_sentences(bank):
    """Fallo real (8-oct-2026, escena documentacion_maestro): «… en 10. Seccion Alpha, y … bajo la ruta 99. Old …»
    se partía en tres trozos y el del medio no tenía respaldo por sí solo."""
    from b5t4.agents.onboarding.v2_content import narration_pairs, split_sentences
    text = ("La Sección Alpha almacena su documentación viva en 10. Seccion Alpha, y toda versión anterior debe "
            "archivarse bajo la ruta 99. Old sin borrar ningún archivo. El maestro tiene la máxima autoridad.")
    assert split_sentences(text) == [
        "La Sección Alpha almacena su documentación viva en 10. Seccion Alpha, y toda versión anterior debe "
        "archivarse bajo la ruta 99. Old sin borrar ningún archivo.", "El maestro tiene la máxima autoridad."]
    assert split_sentences("Hola. ¿Qué tal? Bien.") == ["Hola.", "¿Qué tal?", "Bien."]
    pairs, labels = narration_pairs([("one", text, ["team-01"])], bank)
    assert len(pairs) == 2 and not any(claim.startswith("Seccion Alpha") for claim, _ in pairs)


# ------------------------------------------------------------------ H · ampliación incremental y catálogo acotado
def test_expansion_reads_only_new_evidence_and_keeps_contract():
    from b5t4.agents.onboarding.schemas import Evidence, Fact
    from b5t4.agents.onboarding.v2_content import expand_research
    from b5t4.agents.onboarding.v2_schemas import ResearchDraft
    old = Evidence(id="C1", source="00_CONTEXTO.md", heading="§1", text="TEXTO VIEJO " * 50, page=1, section="1", kind="context")
    new = Evidence(id="D1", source="doc.md", heading="p. 1", text="El maestro se abre el lunes.", page=1, section="", kind="document")
    draft = ResearchDraft(facts=[Fact(text=f"Hecho existente número {i} del capítulo.", source_ids=["C1"]) for i in range(4)],
                          gaps=["No se dice cuándo se abre el maestro."])
    topic = type("Topic", (), {"id": "t", "model_dump_json": lambda self: "{}"})()
    brief = type("Brief", (), {"model_dump_json": lambda self: "{}"})()
    class Client:
        prompts = []
        def __init__(self, ids): self.ids = ids
        def json(self, schema, system, prompt, *, validate=None, **kwargs):
            self.prompts.append(prompt)
            value = ResearchDraft(facts=draft.facts + [Fact(text="El maestro se abre los lunes por la mañana.", source_ids=self.ids)], gaps=[])
            if validate: validate(value)
            return value
    result = expand_research(topic, brief, draft, [new], Client(["D1"]))
    assert len(result.facts) == 5 and result.facts[-1].source_ids == ["D1"]
    assert "TEXTO VIEJO" not in Client.prompts[-1] and "El maestro se abre el lunes." in Client.prompts[-1]   # no relee lo leído
    assert "Hecho existente número 0" in Client.prompts[-1]
    with pytest.raises(ValueError, match="inexistentes"):
        expand_research(topic, brief, draft, [new], Client(["X9"]))
    assert expand_research(topic, brief, draft, [], Client(["D1"])) is draft                                   # nada nuevo: sin llamada


def test_catalog_is_narrowed_to_the_paths_closest_to_the_gaps():
    from b5t4.agents.onboarding.v2_content import focus_catalog
    catalog = [{"path": f"02. Otros/fichero_{i:03d}.md", "kind": "md", "folder": "02. Otros"} for i in range(300)]
    catalog.insert(137, {"path": "10. Seccion Alpha/01. Documentacion/Seccion_Alpha_Maestro_Controles.md", "kind": "md", "folder": "10"})
    narrowed = focus_catalog(catalog, "Faltan los controles del maestro de Alpha", limit=20)
    assert len(narrowed) == 20 and catalog[137] in narrowed
    assert [r["path"] for r in narrowed] == [r["path"] for r in catalog if r in narrowed]                       # orden original
    small = catalog[:10]
    assert focus_catalog(small, "lo que sea", limit=20) == small


def test_stage_recipe_for_incremental_expansion_is_tracked(tmp_path):
    from b5t4.agents.onboarding.schemas import Fact
    from b5t4.agents.onboarding.v2_schemas import ResearchDraft
    artifacts = StageArtifacts(tmp_path, None, "recipe")
    make = lambda: ResearchDraft(facts=[Fact(text=f"Hecho número {i} del capítulo.", source_ids=["C1"]) for i in range(4)])
    first = artifacts.get("ampliado_t.json", ResearchDraft, make, dependencies=["a"])
    calls = []
    again = artifacts.get("ampliado_t.json", ResearchDraft, lambda: calls.append(1) or make(), dependencies=["a"])
    assert again == first and not calls                                                                         # se reutiliza
    artifacts.get("ampliado_t.json", ResearchDraft, lambda: calls.append(1) or make(), dependencies=["b"])
    assert calls == [1]                                                                                          # dependencia nueva: se rehace


def test_default_is_one_claim_per_jev_request(tmp_path, monkeypatch):
    """Con varias afirmaciones por petición Jev aprobó una palabra cambiada (0,92 frente a 0,33 sola)."""
    calls = []
    monkeypatch.setattr(verifier, "available", lambda: True)
    monkeypatch.setattr(verifier, "_ask", lambda *a: pytest.fail("no debe agrupar por defecto"))
    monkeypatch.setattr(verifier, "supports", lambda claim, passage: calls.append(claim) or .9)
    checks = Checks(tmp_path / "run", tmp_path / "shared.json", lambda _: None)
    assert checks.many([("a", "P"), ("b", "P"), ("c", "P")]) == [.9, .9, .9] and sorted(calls) == ["a", "b", "c"]
