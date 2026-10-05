"""
Pruebas de humo de la capa de datos. Se saltan si la carpeta de datos no está disponible en esta máquina
(por ejemplo, en el PC de un compañero que aún no tiene la copia).

    uv run pytest -q
"""
import pytest

from b5t4.config import get_settings
from b5t4.corpus import load_contexts, load_manifest, select, section_index

s = get_settings()
pytestmark = pytest.mark.skipif(not s.manifest_path.exists(), reason=f"sin datos en {s.data_dir}")

TEMPLATE = ["Qué es", "Responsables", "Objetivos", "Entregables y cadencia", "Procesos", "Tipos de archivo e informes",
            "Dónde está cada cosa", "Reglas", "Incoherencias y pendientes", "Preguntas frecuentes", "Fuentes de este documento"]


def test_manifest_loads_and_has_current_files():
    files = load_manifest()
    assert len(files) > 1000
    current = select(files)
    assert current and all(f.is_current for f in current)


def test_every_context_follows_the_template():
    """La plantilla común es la base del troceado del RAG y del guion del onboarding: si alguien la rompe, falla aquí."""
    for doc in load_contexts():
        numbered = [sec.title for sec in doc.sections if sec.number != "Anexo"]
        assert numbered == TEMPLATE, doc.rel


def test_responsables_available_for_all_sections():
    idx = section_index(load_contexts())
    folders = {sec.folder.split("/")[0] for sec in idx["2"]}
    for f in ("10. Seccion Alpha", "13. Seccion Investment Grade", "20. Gestion Clientes"):
        assert f in folders


def test_opinion_editions_found():
    from b5t4.agents.opinion import list_editions

    eds = list_editions()
    assert len(eds) >= 2
    assert eds == sorted(eds, key=lambda e: e.date)
