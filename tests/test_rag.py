"""Pruebas del buscador del agente 3. Las dos primeras no necesitan datos; la última mide el golden set."""
import pytest

from b5t4.agents.rag.index import BM25, tokenize


def test_tokenize_keeps_emails_and_stems_words():
    t = tokenize("Operativa de Luxemburgo: privatedesk@andbank.lu")
    assert "privatedesk@andbank.lu" in t and "privatedesk" in t
    assert tokenize("operativa") == tokenize("operativas")       # misma raíz
    assert "de" not in t                                           # palabra vacía


def test_bm25_prefers_rare_terms():
    docs = [tokenize(x) for x in ("la cartera de la sección", "la cartera del cliente de Luxemburgo", "otra cartera")]
    sc = BM25(docs).scores(tokenize("cartera Luxemburgo"))
    assert max(sc, key=sc.get) == 1


def test_golden_set_sources_in_top_k():
    """Si el buscador empeora (la fuente correcta deja de salir entre los k primeros), falla aquí."""
    import yaml

    from b5t4.agents.rag import search
    from b5t4.config import ROOT, get_settings

    if not get_settings().manifest_path.exists():
        pytest.skip("sin datos")
    qs = [q for q in yaml.safe_load((ROOT / "evals" / "preguntas_rag.yaml").read_text(encoding="utf-8")) if q.get("fuentes")]
    found = sum(any(c.source in q["fuentes"] for _, c in search(q["pregunta"])) for q in qs)
    assert found / len(qs) >= 0.9
