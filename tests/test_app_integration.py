"""Regresiones de integración: onboarding convive con los accesos existentes.

No realizan llamadas de pago ni requieren los datos de OneDrive.
"""
import json

import pytest

from b5t4 import cli
from b5t4.app import ui, ui_onboarding


def test_application_keeps_three_tabs_and_agent_callbacks():
    demo = ui.build()
    try:
        tabs = [component["props"]["label"] for component in demo.config["components"]
                if component["type"] == "tabitem"]
        assert tabs == ["1 · Onboarding", "2 · Opinión Corporativa", "3 · Pregunta"]
        callbacks = {entry.fn for entry in demo.fns.values()}
        assert {ui_onboarding._brief_message, ui_onboarding._personalized,
                ui_onboarding._resume_onboarding, ui._ask} <= callbacks
    finally:
        demo.close()


def test_rag_callback_preserves_citations_audio_and_timings(monkeypatch):
    from b5t4.agents import rag
    from b5t4.agents.rag.answer import Answer, Citation

    calls = []
    def answer(question, voice):
        calls.append((question, voice))
        return Answer(question=question, text="Consulta el manual [1].", mode="llm",
                      citations=[Citation(n=1, source="manual.md", heading="Reglas")],
                      timings={"buscar": .02}, seconds=.5, audio_path="respuesta.wav")
    monkeypatch.setattr(rag, "ask", answer)
    text, audio = ui._ask("¿Dónde están las reglas?", True)
    assert calls == [("¿Dónde están las reglas?", True)]
    assert "manual.md" in text and "Reglas" in text and "buscar 0.02 s" in text
    assert audio == "respuesta.wav"


def test_opinion_tab_survives_agent_errors(monkeypatch):
    """La pestaña 2 llama al agente con sus opciones y, si el agente falla, la interfaz enseña el error en vez de caerse.
    (Antes el agente 2 era un marcador «pendiente»; desde el 7-oct-2026 está implementado y la pestaña pasa
    referencia/vídeo a run().)"""
    from b5t4.agents import opinion

    received = []
    def failing(**kwargs):
        received.append(kwargs)
        raise RuntimeError("sin datos de prueba")
    monkeypatch.setattr(opinion, "run", failing)
    text = ui._safe(ui._opinion, True, False)
    assert received == [{"reference": True}]
    assert "Error" in text and "sin datos de prueba" in text


def test_cli_passes_brief_and_options_to_onboarding(tmp_path, monkeypatch):
    from b5t4.agents import onboarding

    brief = {"role": "Analista junior", "objective": "Conocer el proceso semanal"}
    path = tmp_path / "brief.json"
    path.write_text(json.dumps(brief), encoding="utf-8")
    received = []
    monkeypatch.setattr(onboarding, "run", lambda **kwargs: received.append(kwargs))
    with pytest.raises(SystemExit) as result:
        cli.main(["onboarding", "--brief", str(path), "--report-only"])
    assert result.value.code == 0
    assert received == [{"resume": None, "report_only": True, "brief": brief}]


def test_cli_keeps_rag_eval_from_main(monkeypatch):
    received = []
    monkeypatch.setattr(cli, "cmd_rag_eval", lambda args: received.append(args.answers) or 0)
    with pytest.raises(SystemExit) as result:
        cli.main(["rag", "eval", "--answers"])
    assert result.value.code == 0 and received == [True]


def test_shared_renderer_keeps_all_original_scene_kinds():
    from playwright.sync_api import sync_playwright
    from b5t4.render.schemas import Scene, Storyboard
    from b5t4.render.video import scene_html

    data = {
        "title": {"kicker": "Edición", "title": "Visión corporativa", "subtitle": "Cambios"},
        "kpi": {"cards": [{"label": "Dato", "value": 5, "decimals": 0}]},
        "bars": {"title": "Objetivos", "bars": [{"label": "Actual", "value": 5, "style": "actual"}]},
        "bullets": {"title": "Claves", "items": [{"icon": "1", "text": "Consultar las fuentes"}]},
        "compare": {"title": "Comparación", "rows": [{"label": "Dato", "fmt": "5", "value": 5, "max": 10}], "chip": "Cambio"},
        "close": {"title": "Próximos pasos", "stats": [{"label": "Estado", "value": "Listo"}], "disclaimer": "Consultar la documentación"},
    }
    storyboard = Storyboard(topic="Comparación", scenes=[
        Scene(id=kind, kind=kind, narration="Explicación", data=values)
        for kind, values in data.items()])
    timeline = {"total": 36, "scenes": [
        {"id": scene.id, "start": i * 6, "duration": 6}
        for i, scene in enumerate(storyboard.scenes)]}
    html = scene_html(storyboard, timeline)
    assert "__V2_" not in html and "gsap.timeline" not in html
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            for i, scene in enumerate(storyboard.scenes):
                instant = i * 6 + 3
                page.evaluate("t => render(t)", instant)
                before = page.screenshot()
                page.evaluate("t => render(t)", 35)
                page.evaluate("t => render(t)", instant)
                assert page.screenshot() == before
                assert page.locator("#" + scene.id).evaluate("node => node.innerHTML.length") > 40
            assert not errors
        finally:
            browser.close()
