"""Pruebas de las piezas deterministas de la capa de salida (no necesitan datos ni claves)."""
from b5t4.models.tts import verbalize
from b5t4.render.report import md_to_html
from b5t4.render.schemas import Scene, Storyboard


def test_verbalize_numbers_and_units():
    out = verbalize("El objetivo del bono es 5,00 % y sube 25 pb")
    assert "cinco" in out and "por ciento" in out and "puntos básicos" in out


def test_verbalize_keeps_sentence_end_and_separates_codes():
    assert verbalize("entre el 20 y el 25. Si cae") == "entre el veinte y el veinticinco. Si cae"
    assert verbalize("carteras P1-P4. La Sección") == "carteras P uno-P cuatro. La Sección"
    assert verbalize("pulsa Ctrl+Alt+F9 ahora") == "pulsa Ctrl+Alt+F nueve ahora"
    assert verbalize("61.5 y 1.234") == "sesenta y uno coma cinco y mil doscientos treinta y cuatro"


def test_markdown_table_is_scrollable_on_mobile():
    html = md_to_html("| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<div class="tw"><table>' in html and "<td>1</td>" in html


def test_storyboard_budget():
    sb = Storyboard(topic="t", scenes=[Scene(id="s1", kind="title", narration="palabra " * 230)])
    assert 95 < sb.estimated_seconds(2.3) < 105
