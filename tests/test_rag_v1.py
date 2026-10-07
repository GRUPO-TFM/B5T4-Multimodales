"""Pruebas del RAG v1 (verificación frase a frase y fusión híbrida). No necesitan datos, claves ni modelos."""
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


def test_rrf_rewards_agreement_between_retrievers():
    a, b, c, d = (_chunk(x) for x in "abcd")
    lexical = [(9.0, a), (8.0, b), (7.0, c)]
    dense = [(0.9, c), (0.8, b), (0.7, d)]
    fused = [ch.id for _, ch in rrf([lexical, dense], k=4)]
    assert fused[0] in ("b", "c")          # salen en las dos listas
    assert set(fused) == {"a", "b", "c", "d"}
