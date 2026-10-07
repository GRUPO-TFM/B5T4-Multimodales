"""V2: personalización, presupuesto, compatibilidad y render reproducible sin APIs."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from b5t4.agents.onboarding import conversation, pipeline
from b5t4.agents.onboarding.material import Material
from b5t4.agents.onboarding.v2_content import cited_passage, validate_modules, Checks, repair_narrations
from b5t4.agents.onboarding.v2_media import common_storyboard, previews, fit_audio_tempo, narrate, cached_timeline
from b5t4.agents.onboarding.v2_pipeline import validate_resume, StageArtifacts, _hash, ExecutionLease
from b5t4.agents.onboarding.v2_schemas import (OnboardingBrief, BriefReply, DirectedStoryboard,
    FactBank, FactChapter, VisualModule)
from b5t4.agents.onboarding.schemas import VerifiedFact
from b5t4.config import Settings
from b5t4.models.openrouter import UsageLedger, BudgetExceeded, OpenRouter


def test_json_reserves_reasoning_space_and_recovers_from_length(tmp_path, monkeypatch):
    from b5t4.agents.onboarding.schemas import SourceSelection
    client = OpenRouter(tmp_path, log=lambda _: None)
    payloads = []
    monkeypatch.setattr(client, "estimate", lambda *args, **kwargs: .01)
    def request(endpoint, payload, stage, estimate):
        payloads.append(payload)
        if len(payloads) == 1:
            return {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"document_paths":[]}'}}]}
    monkeypatch.setattr(client, "_request", request)
    result = client.json(SourceSelection, "Selecciona fuentes", "Catálogo vacío", max_output=1200)
    assert result.document_paths == []
    assert payloads[0]["reasoning"] == {"effort": "low"}
    assert payloads[1]["max_tokens"] == 2 * payloads[0]["max_tokens"]


def test_resume_revalidates_legacy_research_and_retains_provenance(tmp_path):
    from b5t4.agents.onboarding.schemas import SourceSelection
    (tmp_path / "ampliacion_team.json").write_text('{"document_paths":[]}', encoding="utf-8")
    dependency = {"profile": "operativo"}
    (tmp_path / "etapas.json").write_text(json.dumps({"ampliacion_team.json": _hash(["old", dependency])}), encoding="utf-8")
    store = StageArtifacts(tmp_path, "old", "new")
    checked = []
    def create(): raise AssertionError("No debe repetir la llamada pagada")
    store.get("ampliacion_team.json", SourceSelection, create, lambda value: checked.append(value), dependency)
    assert checked and store.metadata["ampliacion_team.json"]["origin_recipe_hash"] == "old"
    result = store.get("ampliacion_team.json", SourceSelection, lambda: SourceSelection(document_paths=["new.pdf"]),
                      dependencies={"profile": "responsable"})
    assert result.document_paths == ["new.pdf"]


def test_unverified_relation_becomes_map_without_weakening_fact_gate(bank):
    module = VisualModule(kind="organisation", title="Equipo", items=[
        {"id":"ana","label":"Ana","claim_ids":["team-01"]},
        {"id":"luis","label":"Luis","claim_ids":["team-01"]}],
        edges=[{"from_id":"ana","to_id":"luis","claim_ids":["team-01"]}])
    class Gate:
        def many(self,pairs): return [.1 if "jerárquicamente" in claim else .99 for claim,_ in pairs]
        def require(self,pairs,labels):
            assert all(value >= .8 for value in self.many(pairs))
    validate_modules([module],bank,Gate(),repair_relationships=True)
    assert module.kind=="map" and not module.edges


def test_shared_jev_cache_reuses_passage_across_instances(tmp_path, monkeypatch):
    from b5t4.models import verifier
    calls=[]
    monkeypatch.setattr(verifier,"available",lambda:True)
    monkeypatch.setattr(verifier,"supports",lambda claim,passage:calls.append(claim) or .95)
    first=Checks(tmp_path/'one',tmp_path/'shared.json',lambda _:None)
    second=Checks(tmp_path/'two',tmp_path/'shared.json',lambda _:None)
    assert first.check('Ana trabaja en el equipo.','Ana trabaja en el equipo.')==.95
    assert second.check('Ana trabaja en el equipo.','Ana trabaja en el equipo.')==.95
    assert len(calls)==1 and second.stats['cache_hits']==1


def test_residual_audio_tempo_preserves_whole_track_and_rejects_large_changes(tmp_path):
    import numpy as np
    import soundfile as sf
    rate=24000; seconds=62
    samples=(.1*np.sin(2*np.pi*220*np.arange(rate*seconds)/rate)).astype('float32')
    sf.write(tmp_path/'voz.wav',samples,rate)
    timeline={"total":seconds,"scenes":[{"id":"one","start":0,"duration":seconds,"voice_seconds":seconds,"audio":"one.wav"}]}
    result=fit_audio_tempo(timeline,tmp_path,60,lambda _:None)
    assert 54<=result['total']<60 and result['scenes'][0]['duration']==result['total']
    assert result['scenes'][0]['source_voice_seconds']==seconds
    with pytest.raises(ValueError): fit_audio_tempo({"total":90},tmp_path,60,lambda _:None)


def test_progress_does_not_restore_old_conversation_state(monkeypatch):
    import gradio as gr
    from b5t4.app import ui_onboarding as ui
    state=conversation.new_session(); state['draft']={"instructions":""}
    monkeypatch.setattr(ui,'_onboarding',lambda **kwargs:iter([('inicio','',None,None,[]),('fin','',None,None,[])]))
    events=list(ui._personalized(state,'Analista','Junior','Conocer el equipo y sus controles','Alpha',2,5,False))
    assert events[0][0]['confirmed']
    assert events[1][0]==gr.skip() and events[1][1]==gr.skip()


def test_narration_repairs_only_affected_text_and_stops_after_two_rounds(bank):
    from types import SimpleNamespace
    from b5t4.agents.onboarding.v2_schemas import CitedText
    class Gate:
        log=staticmethod(lambda _:None)
        def many(self,pairs): return [.2 if 'dirige' in claim else .99 for claim,_ in pairs]
    class Client:
        calls=0
        def json(self,*args,**kwargs):
            self.calls+=1
            return CitedText(text='Ana y Luis trabajan en el equipo.',claim_ids=['team-01'])
    scene=SimpleNamespace(id='one',narration='Ana dirige a Luis en el equipo.',claim_ids=['team-01'],kind='map')
    client=Client(); result=repair_narrations(SimpleNamespace(scenes=[scene]),bank,client,Gate())
    assert client.calls==1 and result.scenes[0].kind=='map' and 'trabajan' in scene.narration
    class WrongClient(Client):
        def json(self,*args,**kwargs):
            self.calls+=1
            return CitedText(text='Ana dirige a Luis en el equipo.',claim_ids=['team-01'])
    wrong=WrongClient(); scene.narration='Ana dirige a Luis en el equipo.'
    with pytest.raises(ValueError): repair_narrations(SimpleNamespace(scenes=[scene]),bank,wrong,Gate())
    assert wrong.calls==2


def test_audio_resume_requires_matching_text_clips_and_track(tmp_path):
    import numpy as np
    from types import SimpleNamespace
    scene=SimpleNamespace(id='one',kind='hero',narration='Ana trabaja en el equipo.')
    plan=SimpleNamespace(scenes=[scene])
    class Client:
        ledger=SimpleNamespace(entries=[{'generation_id':'gen-test'}])
        def speech(self,*args,**kwargs):
            samples=(np.sin(np.arange(24000)*.1)*4000).astype('<i2')
            return samples.tobytes(),24000
    timeline=narrate(plan,None,Client(),tmp_path,lambda _:None)
    assert cached_timeline(plan,tmp_path)['voice_sha256']==timeline['voice_sha256']
    scene.narration='Ana trabaja en otra organización.'
    assert cached_timeline(plan,tmp_path) is None


def test_one_process_owns_each_execution_folder(tmp_path):
    first=ExecutionLease(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='en curso'): ExecutionLease(tmp_path)
    finally: first.close()
    second=ExecutionLease(tmp_path); second.close()


def brief(**kwargs):
    return OnboardingBrief(role="Analista junior", objective="Conocer el proceso semanal y sus controles", **kwargs)


@pytest.fixture
def bank():
    return FactBank(title="Guía del equipo", chapters=[FactChapter(id="team", title="Equipo", purpose="Conocer el equipo", common=True,
        facts=[VerifiedFact(id="team-01", text="Ana y Luis trabajan en el equipo.", source_ids=["E1"], probability=.99, status="publicar"),
               VerifiedFact(id="team-02", text="Se abre el maestro antes de validar el control.", source_ids=["E2"], probability=.99, status="publicar"),
               VerifiedFact(id="team-03", text="Se envía el informe al equipo.", source_ids=["E2"], probability=.2, status="descartar")])])


@pytest.mark.parametrize("seconds", [59, 301])
def test_brief_rejects_duration_outside_allowed_range(seconds):
    with pytest.raises(ValidationError): brief(duration_seconds=seconds)


def test_brief_does_not_admit_visual_overrides():
    with pytest.raises(ValidationError): brief(palette="blue")


def test_chat_sessions_do_not_share_mutable_history(tmp_path, monkeypatch):
    class FakeClient:
        def __init__(self, out, *args):
            self.out = tmp_path / out.name
        def json(self, schema, system, prompt, **kwargs):
            history = json.loads(prompt)
            return BriefReply(draft={"role": history[-1]["content"], "objective": "Conocer los procedimientos del equipo"},
                              message="Puedes revisar los campos y confirmar el encargo.")
    monkeypatch.setattr(conversation, "OpenRouter", FakeClient)
    a, _ = conversation.chat("Analista de Alpha")
    b, _ = conversation.chat("Responsable de equipo")
    snapshot = copy.deepcopy(a)
    updated, _ = conversation.chat("Analista con experiencia", a)
    assert a == snapshot and a["id"] != b["id"]
    assert updated["draft"]["role"] == "Analista con experiencia"
    assert b["draft"]["role"] == "Responsable de equipo"


def test_confirmation_uses_edited_profile_and_starts_new_chat_after_confirmation(tmp_path, monkeypatch):
    state = conversation.new_session(); state["draft"] = {"instructions": "Priorizar controles"}
    confirmed, result = conversation.confirm(state, role="Gestor senior", experience="Diez años de experiencia",
        objective="Conocer las reglas del equipo y sus responsabilidades", area="Carteras", minutes=5)
    assert result.role == "Gestor senior" and result.duration_seconds == 300
    assert confirmed["confirmed"] and not state["confirmed"]


def test_ledger_reserves_before_call_and_keeps_uncertain_charges(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json", .1, log=lambda _: None)
    first = ledger.reserve("voz", "model", .07)
    ledger.settle(first, "", None, error="timeout")
    loaded = UsageLedger(ledger.path, .1, log=lambda _: None)
    assert loaded.spent == .07
    with pytest.raises(BudgetExceeded): loaded.reserve("imagen", "model", .04)


def test_ledger_reconciles_actual_cost_and_survives_resume(tmp_path):
    ledger = UsageLedger(tmp_path / "usage.json", 1, log=lambda _: None)
    first = ledger.reserve("texto", "model", .2)
    ledger.settle(first, "gen-1", None)
    ledger.reconcile(lambda _: .03)
    loaded = UsageLedger(ledger.path, 1, log=lambda _: None)
    assert loaded.spent == pytest.approx(.03)
    assert loaded.entries[0]["actual_usd"] == .03


def test_tts_sends_direction_separately_and_uses_pcm(tmp_path, monkeypatch):
    client = OpenRouter(tmp_path, 5, log=lambda _: None)
    received = []
    class Response:
        headers = {"Content-Type": "audio/pcm;rate=24000;channels=1"}
        content = b"\x00\x01" * 1000
    def request(endpoint, payload, *args, **kwargs):
        received.append(payload); return Response()
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(client, "estimate", lambda *a, **k: .02)
    blob, rate = client.speech("Bienvenido al equipo.", "Warm and professional", seconds=10)
    assert rate == 24000 and blob == Response.content
    payload = received[0]
    assert payload["input"] == "Bienvenido al equipo." and payload["response_format"] == "pcm"
    assert "speed" not in payload and "Warm" not in payload["input"]
    assert payload["provider"]["options"]["google-ai-studio"]["speech_metadata"]["style"] == "Warm and professional"


def test_derivatives_reject_discarded_facts(bank):
    with pytest.raises(ValueError, match="no publicados"): cited_passage(["team-03"], bank)
    from types import SimpleNamespace
    from b5t4.agents.onboarding.v2_content import validate_storyboard
    plan=synthetic_storyboard()
    plan.scenes[0].image_id='visible'; plan.scenes[1].image_id='unused-in-map'
    direction=SimpleNamespace(illustrations=[SimpleNamespace(id='visible'),SimpleNamespace(id='unused-in-map')])
    class Gate:
        def many(self,pairs): return [.99 for _ in pairs]
        def require(self,pairs,labels): pass
    validate_storyboard(plan,bank,direction,Gate())
    assert {scene.image_id for scene in plan.scenes if scene.image_id}=={'visible'}


def test_process_order_is_checked_even_without_explicit_edges(bank):
    module = VisualModule(kind="process", title="Proceso semanal", items=[
        {"id": "open", "label": "Abrir el maestro", "claim_ids": ["team-02"]},
        {"id": "check", "label": "Validar el control", "claim_ids": ["team-02"]}])
    received=[]
    class Checks:
        def require(self, pairs, labels): received.extend(pairs)
    validate_modules([module], bank, Checks())
    assert any("precede en el proceso" in claim for claim, _ in received)


def test_resume_refuses_changed_brief_and_sources(tmp_path):
    data = tmp_path / "data"; data.mkdir()
    out = tmp_path / "run"; out.mkdir()
    m = Material(Settings(data_dir=data), [])
    (out / "ejecucion.json").write_text(json.dumps({"inputs": {"role": "junior"}}))
    with pytest.raises(ValueError, match="encargo"): validate_resume(out, {"role": "senior"}, m)
    (out / "fuentes.json").write_text(json.dumps({"sha256": {"manual.md": "old"}, "documents_read": []}))
    (data / "manual.md").write_text("Nuevo contenido")
    with pytest.raises(ValueError, match="fuente"): validate_resume(out, {"role": "junior"}, m)


def test_dispatch_resumes_v2_and_keeps_v1_api(tmp_path, monkeypatch):
    from b5t4.agents.onboarding import v2_pipeline
    (tmp_path / "brief.json").write_text(brief().model_dump_json(), encoding="utf-8")
    received=[]
    monkeypatch.setattr(v2_pipeline, "run", lambda *args, **kwargs: received.append((args,kwargs)) or tmp_path)
    assert pipeline.run(resume=tmp_path) == tmp_path
    assert received[0][0][0]["role"] == "Analista junior"


def synthetic_storyboard():
    scenes=[]
    for index, kind in enumerate(["hero", "map", "process", "close"]):
        items=[{"id":"open","label":"Abrir el maestro","detail":"Conectar el terminal.","claim_ids":["team-02"]}]
        if kind in ("map","process"):
            items.append({"id":"check","label":"Validar el control","detail":"Comprobar la señal del control.","claim_ids":["team-02"]})
        scenes.append({"id":f"s{index}","kind":kind,"title":"Una incorporación clara y cercana",
            "items":items,"edges":[],"narration":"Conoce el proceso y las personas del equipo para trabajar con claridad.",
            "claim_ids":["team-02"],"transition":"diagonal" if index==1 else "fade","movement":"trace"})
    return DirectedStoryboard(scenes=scenes)


def test_gsap_render_is_deterministic_and_uses_local_brand_resources(tmp_path, bank):
    sb = common_storyboard(synthetic_storyboard(), brief(), bank, {"E1":1,"E2":2}, {})
    timeline={"total":24,"scenes":[{"id":scene.id,"start":index*6,"duration":6,"kind":scene.kind} for index,scene in enumerate(sb.scenes)]}
    images, bounds = previews(sb, timeline, tmp_path)
    assert len(images)==4 and not bounds
    html=(tmp_path/'escenas.html').read_text(encoding='utf-8')
    assert '#D52B1E' in html and 'data:image/png;base64' in html and 'gsap.timeline' in html
    assert '__V2_' not in html


def test_six_focus_items_fit_and_transitions_survive_backward_seeks(tmp_path, bank):
    from b5t4.agents.onboarding.v2_schemas import VisualItem
    plan=synthetic_storyboard()
    focus=plan.scenes[1].model_copy(deep=True)
    focus.id='focus-six'; focus.kind='focus'
    focus.items=[VisualItem(id=f'item-{i}',label='Responsabilidades y herramientas del equipo',
        detail='Consultar las responsabilidades documentadas del equipo y revisar las herramientas de trabajo que corresponden a cada proceso operativo.',claim_ids=['team-02']) for i in range(6)]
    plan.scenes.insert(2,focus)
    sb=common_storyboard(plan,brief(),bank,{'E1':1,'E2':2},{})
    timeline={'total':30,'scenes':[{'id':s.id,'start':i*6,'duration':6,'kind':s.kind} for i,s in enumerate(sb.scenes)]}
    images,bounds=previews(sb,timeline,tmp_path)
    assert len(images)==5 and not bounds
    assert len(json.loads((tmp_path/'validacion_diseno.json').read_text(encoding='utf-8'))['transition_samples'])==20
