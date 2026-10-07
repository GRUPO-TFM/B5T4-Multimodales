"""
Agente 2 (Opinión Corporativa). Se prueba todo lo que no es LLM con la extracción de referencia
(evals/opinion_referencia.json): selección de ediciones, comparación e informe. Se salta si no hay datos.
"""
import pytest

from b5t4.agents.opinion.catalog import fmt_es, row_label
from b5t4.agents.opinion.compare import _nums, row_key
from b5t4.config import get_settings


def test_region_and_view_formatting():
    from b5t4.agents.opinion.compare import _fmt_view
    from b5t4.agents.opinion.extract import detect_region
    from b5t4.agents.opinion.schemas import View

    # «ust» no cuenta dentro de «ajuste»/«robusto»: la región sale de las palabras enteras del bloque
    txt = "COYUNTURA ... un ajuste robusto ... Perspectivas de mercado: recomendaciones y objetivos. Renta variable (Stoxx Europe): NEUTRAL. Bund: NEUTRAL"
    assert detect_region(txt) == "Europa"
    oil = View(asset_id="oil", label="Petróleo (WTI)", region="Materias primas", stance="OTRA", stance_raw="Banda objetivo: 80-90 USD/barril",
               target_raw="80-90 USD/barril (Comprar por debajo de 80 USD; vender por encima de 90 USD)", page=20)
    assert _fmt_view(oil) == "80-90 USD/barril"                     # ni duplicado ni regla operativa para el cliente


def test_helpers_without_data():
    assert row_label("Spain - 10yr Gov bond") == "España 10 años"
    assert row_label("Mexico - 10yr Govie (USD)") == "México 10 años (USD)"
    assert row_key("Singapore - 10yr Gov bond (loc") == row_key("Singapore - 10yr Gov bond")
    assert row_key("Mexico - 10yr Govie (Loc)") != row_key("Mexico - 10yr Govie (USD)")
    assert _nums("rend. objetivo: 4,5 %") == _nums("rendimiento objetivo: 4,50%")
    assert _nums("objetivo: 1.600") == [1600.0]
    assert _nums("objetivo para el cierre de 2026: 1.600") == _nums("objetivo para el cierre de 2027: 1.600") == [1600.0]   # el año no es un objetivo
    assert _nums("nivel 2.050") == [2050.0]
    assert fmt_es(19584) == "19.584" and fmt_es(4.25) == "4,25" and fmt_es(10, rate=True) == "10,00"


needs_data = pytest.mark.skipif(not get_settings().manifest_path.exists(), reason="sin datos")


@needs_data
def test_latest_two_are_3T_and_4T_2026():
    from b5t4.agents.opinion.select import latest_two

    a, b = latest_two(log=lambda *_: None)
    assert (a.label, b.label) == ("3T 2026", "4T 2026")


@needs_data
def test_compare_finds_the_known_changes(tmp_path):
    from b5t4.agents.opinion.compare import compare
    from b5t4.agents.opinion.explain import explain
    from b5t4.agents.opinion.extract import load_reference
    from b5t4.agents.opinion.report import build
    from b5t4.agents.opinion.select import latest_two

    a_ed, b_ed = latest_two(log=lambda *_: None)
    a, b = load_reference(a_ed), load_reference(b_ed)
    ch = compare(a, b)
    stance = {c.id: (c.before.split()[0], c.after.split()[0], c.direction) for c in ch if c.kind == "postura"}
    assert stance == {"v:us.govt10y": ("NEUTRAL", "SOBREPONDERAR", "mejora"),
                      "v:eu.equity": ("NEUTRAL-INFRAPONDERAR", "NEUTRAL-SOBREPONDERAR", "mejora"),
                      "v:cn.equity_shenzhen": ("NEUTRAL", "INFRAPONDERAR", "empeora")}
    assert sum(c.kind == "desaparece" and c.group == "Israel" for c in ch) == 4
    assert {c.kind for c in ch if c.group == "Tendencias estructurales"} == {"tendencia_nueva", "tendencia_sale"}
    ust = next(c for c in ch if c.id == "v:us.govt10y")
    assert (ust.delta, ust.delta_unit) == (50, "pb")
    assert not any("tierras raras" in c.label.lower() for c in ch)       # POSITIVA → FAVORABLE no es un cambio
    changes, summary = explain(ch, a, b, use_llm=False, verify=False, log=lambda *_: None)   # sin red: frases factuales
    files = build(a, b, changes, summary, tmp_path, {"verified": "test"})
    html = files["html"].read_text(encoding="utf-8")
    assert "SOBREPONDERAR" in html and "data:image/png;base64" in html and "Aviso legal" in html
    assert len(files["png"]) == 3 and files["json"].exists()


@needs_data
def test_storyboard_from_changes(tmp_path):
    """El guion del vídeo sale de cambios.json, cabe en el presupuesto y solo usa escenas que la plantilla sabe dibujar."""
    import json

    from b5t4.agents.opinion.compare import compare
    from b5t4.agents.opinion.explain import explain
    from b5t4.agents.opinion.extract import load_reference
    from b5t4.agents.opinion.report import build
    from b5t4.agents.opinion.select import latest_two
    from b5t4.agents.opinion.video import TEMPLATE, build_storyboard
    from b5t4.config import get_settings

    a_ed, b_ed = latest_two(log=lambda *_: None)
    a, b = load_reference(a_ed), load_reference(b_ed)
    changes, summary = explain(compare(a, b), a, b, use_llm=False, verify=False, log=lambda *_: None)
    build(a, b, changes, summary, tmp_path, {"verified": "test"})
    sb = build_storyboard(json.loads((tmp_path / "cambios.json").read_text(encoding="utf-8")))
    kinds = {sc.kind for sc in sb.scenes}
    assert kinds <= {"title", "shift", "hbars", "cards", "close"} and sb.scenes[0].kind == "title" and sb.scenes[-1].kind == "close"
    assert sum(sc.kind == "shift" for sc in sb.scenes) >= 3
    assert sb.estimated_seconds() <= get_settings().max_seconds
    text = " ".join(sc.narration for sc in sb.scenes)
    assert "(p." not in text and "…" not in text and "4T 2026" not in text      # nada truncado ni siglas para la voz
    assert TEMPLATE.exists()
