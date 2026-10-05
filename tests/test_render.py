"""Pruebas de las piezas deterministas de la capa de salida (no necesitan datos ni claves)."""
from b5t4.models.tts import verbalize
from b5t4.render.report import md_to_html
from b5t4.render.schemas import Scene, Storyboard


def test_verbalize_numbers_and_units():
    out = verbalize("El objetivo del bono es 5,00 % y sube 25 pb")
    assert "cinco" in out and "por ciento" in out and "puntos básicos" in out


def test_markdown_table_is_scrollable_on_mobile():
    html = md_to_html("| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<div class="tw"><table>' in html and "<td>1</td>" in html


def test_storyboard_budget():
    sb = Storyboard(topic="t", scenes=[Scene(id="s1", kind="title", narration="palabra " * 230)])
    assert 95 < sb.estimated_seconds(2.3) < 105
