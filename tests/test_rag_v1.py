"""Pruebas del RAG v1 (verificación frase a frase y fusión híbrida). No necesitan datos, claves ni modelos."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from b5t4.agents.rag.hybrid import rrf
from b5t4.agents.rag.index import Chunk
from b5t4.agents.rag.verify import WARN, check_sentences, cited, rebuild, split_sentences

LUX = ("La operativa de Luxemburgo se debe enviar a privatedesk@andbank.lu [1], [2]. Asimismo, debe incluirse en "
       "copia (Cc) a middle.office@andbank.lu [1], [2] y al banquero del cliente, banquero.x@andbank.es [1], [2].")


def _chunk(i: str, text: str = "") -> Chunk:
    return Chunk(id=i, text=text or i, source=f"{i}.md", folder="f", section="s", heading="h", kind="contexto")


def test_split_keeps_citations_and_emails():
    s = split_sentences(LUX)
    assert len(s) == 2
    assert s[0].endswith("[1], [2].") and "privatedesk@andbank.lu" in s[0]
    assert cited(s[1], 2) == [1, 2] and cited("dato [3] [9]", 3) == [3]


def test_unsupported_sentence_is_removed_and_doubtful_flagged():
    passages = [_chunk("a", "Enviar a privatedesk@andbank.lu con copia a middle.office@andbank.lu y al banquero."),
                _chunk("b", "Reglas operativas de Luxemburgo.")]
    # Jev simulado: respalda la 1.ª frase, duda de la 2.ª (el correo concreto del banquero no está en la fuente)
    fake = lambda claim, passage: 0.95 if "privatedesk" in claim else 0.5
    tri = lambda p: "publicar" if p >= 0.8 else ("descartar" if p < 0.3 else "revisar")
    checks = check_sentences(LUX, passages, supports=fake, triage=tri)
    assert [c.decision for c in checks] == ["publicar", "revisar"]
    out = rebuild(checks)
    assert out.count(WARN) == 1 and "privatedesk" in out

    checks[1].decision = "descartar"
    assert "banquero.x" not in rebuild(checks)


def test_sentence_without_citation_needs_review():
    checks = check_sentences("Esto no cita nada.", [_chunk("a")], supports=lambda *_: 1.0, triage=lambda p: "publicar")
    assert checks[0].decision == "revisar" and checks[0].p is None


def test_initials_do_not_split_sentences():
    hy = ("La gestión corre a cargo de Juan Ramón Casanovas [4] y J. Lissignoli (externo) [4], [8]. "
          "Por su parte, los informes los hace Javier Hernández [4].")
    s = split_sentences(hy)
    assert len(s) == 2 and "J. Lissignoli" in s[0]


def test_no_consta_sentence_is_not_flagged():
    text = "La operativa va a privatedesk@andbank.lu [1]. No consta en la documentación."
    checks = check_sentences(text, [_chunk("a")], supports=lambda *_: 0.95,
                             triage=lambda p: "publicar" if p >= 0.8 else "revisar")
    assert [c.decision for c in checks] == ["publicar", "sin verificar"]
    assert WARN not in rebuild(checks)


@pytest.mark.parametrize("text", [
    "El teléfono de Ana es 600123456, aunque no consta en la documentación.",
    "No consta en la documentación, pero escribe a inventado@example.com.",
    "No consta en la documentación. [9]",
    "El teléfono móvil de Ana no consta en la documentación.",
])
def test_no_consta_does_not_exempt_other_uncited_claims(text):
    def must_not_verify(*_):
        raise AssertionError("Una frase sin fuente no puede verificarse")

    checks = check_sentences(text, [_chunk("a")], supports=must_not_verify)
    assert checks[0].decision == "revisar"
    assert WARN in rebuild(checks)


@pytest.mark.parametrize("text", ["No consta.", "No consta en la documentación.", "NO CONSTA EN LA DOCUMENTACIÓN"])
def test_canonical_abstention_needs_no_citation(text):
    checks = check_sentences(text, [])
    assert checks[0].decision == "sin verificar"
    assert WARN not in rebuild(checks)


@pytest.mark.parametrize("suffix", ["[1]", "[1], [2]", "[1][2]"])
def test_split_keeps_citations_after_punctuation_on_previous_sentence(suffix):
    first = f"Ana gestiona Alpha. {suffix}"
    second = "Luis gestiona Beta. [2]"
    assert split_sentences(f"{first} {second}") == [first, second]


def test_supported_claim_survives_when_next_claim_is_discarded():
    checks = check_sentences(
        "Ana gestiona Alpha. [1] Luis gestiona Beta. [2]",
        [_chunk("a", "Ana gestiona Alpha."), _chunk("b", "Beta no tiene responsable.")],
        supports=lambda claim, passage: .95 if "Ana" in claim else .1,
        triage=lambda p: "publicar" if p >= .8 else "descartar",
    )
    assert [c.cites for c in checks] == [[1], [2]]
    assert rebuild(checks) == "Ana gestiona Alpha. [1]"


def test_explicit_empty_hits_do_not_trigger_another_search(tmp_path, monkeypatch):
    from b5t4.agents.rag import answer
    from b5t4.config import Settings

    monkeypatch.setattr(answer, "get_settings", lambda: Settings(data_dir=tmp_path))
    def must_not_search(*_):
        raise AssertionError("La búsqueda ya ha terminado sin resultados")
    monkeypatch.setattr(answer, "search", must_not_search)
    res = answer.ask("Una pregunta sin resultados", hits=[])
    assert not res.found and res.text == answer.NO_CONSTA


@pytest.mark.parametrize("second_verified", [False, True])
def test_concurrent_questions_keep_their_own_retrieval(tmp_path, monkeypatch, second_verified):
    from b5t4.agents.rag import answer, verify
    from b5t4.config import Settings
    from b5t4.models import llm

    started, release = Event(), Event()
    a, b = _chunk("a", "Documento de la pregunta A"), _chunk("b", "Documento de la pregunta B")
    settings = Settings(data_dir=tmp_path, openrouter_api_key="offline-test")
    monkeypatch.setattr(answer, "get_settings", lambda: settings)
    searches, prompts = [], {}
    def search_b(question, k=None):
        searches.append(question)
        return [(1.0, b)]
    monkeypatch.setattr(answer, "search", search_b)

    def fake_llm(schema, system, user, log):
        question = user.splitlines()[0].removeprefix("Pregunta: ")
        prompts[question] = user
        if question == "A":
            started.set()
            assert release.wait(5), "La segunda petición quedó bloqueada"
        return schema(found=True, text="Respuesta respaldada [1].", used=[1])
    monkeypatch.setattr(llm, "ask_json", fake_llm)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(verify.ask_verified, "A", verify=False, search_fn=lambda *_: [(1.0, a)])
        try:
            assert started.wait(5)
            if second_verified:
                second = pool.submit(verify.ask_verified, "B", verify=False, search_fn=search_b)
            else:
                second = pool.submit(answer.ask, "B")
            result = second.result(timeout=5)
        finally:
            release.set()
        first_result = first.result(timeout=5)

    second_answer = result.answer if second_verified else result
    assert first_result.answer.citations[0].source == "a.md"
    assert second_answer.citations[0].source == "b.md"
    assert "b.md" in prompts["B"] and "a.md" not in prompts["B"]
    assert searches == ["B"]
    assert answer.search is search_b


def test_rrf_rewards_agreement_between_retrievers():
    a, b, c, d = (_chunk(x) for x in "abcd")
    lexical = [(9.0, a), (8.0, b), (7.0, c)]
    dense = [(0.9, c), (0.8, b), (0.7, d)]
    fused = [ch.id for _, ch in rrf([lexical, dense], k=4)]
    assert fused[0] in ("b", "c")          # salen en las dos listas
    assert set(fused) == {"a", "b", "c", "d"}
