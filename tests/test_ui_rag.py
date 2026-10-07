"""Regresiones de entrada de audio del RAG, sin Whisper ni llamadas a APIs."""
from b5t4.agents.rag.answer import Answer
from b5t4.agents.rag.verify import VerifiedAnswer
from b5t4.agents.rag import verify
from b5t4.app import ui_rag


def fake_rag(monkeypatch):
    questions = []
    def ask(question, **kwargs):
        questions.append(question)
        ans = Answer(question=question, text="Respuesta", mode="extractivo")
        return VerifiedAnswer(answer=ans, text=ans.text)
    monkeypatch.setattr(verify, "ask_verified", ask)
    return questions


def test_new_audio_uses_new_transcription(monkeypatch):
    questions = fake_rag(monkeypatch)
    monkeypatch.setattr(ui_rag, "_transcribe", lambda path: (f"Pregunta de {path}", .1))
    first = ui_rag.answer_audio("primero.wav", "BM25 (palabras exactas)", True, False)
    second = ui_rag.answer_audio("segundo.wav", "BM25 (palabras exactas)", True, False)
    assert first[0] == "Pregunta de primero.wav"
    assert second[0] == "Pregunta de segundo.wav"
    assert questions == [first[0], second[0]]


def test_typed_correction_does_not_transcribe_previous_audio(monkeypatch):
    questions = fake_rag(monkeypatch)
    def must_not_transcribe(path):
        raise AssertionError("El audio anterior no debe bloquear la pregunta escrita")
    monkeypatch.setattr(ui_rag, "_transcribe", must_not_transcribe)
    question, text, audio = ui_rag.answer("anterior.wav", "  Pregunta corregida  ",
                                        "BM25 (palabras exactas)", True, False)
    assert question == "Pregunta corregida" and questions == [question]
    assert "Error" not in text and audio is None


def test_upload_and_recording_share_new_question_callback():
    demo = ui_rag.build()
    try:
        audio = next(c for c in demo.config["components"]
                     if c["type"] == "audio" and c["props"]["label"] == "Pregunta por voz")
        callbacks = {entry.fn for entry in demo.fns.values()}
        assert ui_rag.answer_audio in callbacks
        events = {event: dependency for dependency in demo.config["dependencies"]
                  for component_id, event in dependency["targets"] if component_id == audio["id"]}
        assert {"upload", "stop_recording"} <= events.keys()
        for event in ("upload", "stop_recording"):
            dependency = events[event]
            assert demo.fns[dependency["id"]].fn is ui_rag.answer_audio
            assert len(dependency["inputs"]) == 4  # audio y opciones; no el texto anterior
    finally:
        demo.close()
