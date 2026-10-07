"""
Interfaz del agente 3 (RAG) v1: preguntar HABLANDO o escribiendo, con verificación y elección de buscador.

    uv run python -m b5t4.app.ui_rag            → http://127.0.0.1:7861
    uv run python -m b5t4.app.ui_rag --share    → enlace público temporal

Va aparte de app/ui.py para no tocar la interfaz común mientras el equipo integra. Para montarla como pestaña
en ui.py basta con: `with gr.Tab("3 · Pregunta (v1)"): ui_rag.build_tab()`.

Flujo: micrófono → Whisper (local) → buscador (BM25 o híbrido BM25 + EmbeddingGemma 2) → LLM con citas →
Jev frase a frase → voz (Kokoro). Solo presentación: la lógica está en agents/rag y models.
"""
from __future__ import annotations

import argparse
import time
import traceback

RETRIEVERS = {"BM25 (palabras exactas)": "bm25", "Híbrido: BM25 + EmbeddingGemma 2 (texto e imagen)": "hybrid"}
ICON = {"publicar": "✅", "revisar": "⚠️", "descartar": "❌", "sin verificar": "·"}


def _search_fn(name: str):
    from ..agents.rag.index import search

    if name == "hybrid":
        from ..agents.rag.hybrid import search_hybrid

        return search_hybrid
    return search


def _transcribe(audio_path: str | None) -> tuple[str, float]:
    if not audio_path:
        return "", 0.0
    from ..models.stt_whisper import transcribe_timed

    return transcribe_timed(audio_path)


def answer(audio_path, typed: str, retriever: str, verify: bool, voice: bool):
    """Devuelve (pregunta, respuesta en Markdown, audio). Nunca lanza: la demo no debe caerse."""
    try:
        t0 = time.perf_counter()
        question = (typed or "").strip()
        t_stt = 0.0
        if not question:
            question, t_stt = _transcribe(audio_path)
        if not question:
            return "", "Graba una pregunta o escríbela.", None
        from ..agents.rag.verify import ask_verified

        res = ask_verified(question, voice=voice, search_fn=_search_fn(RETRIEVERS.get(retriever, "bm25")),
                           verify=verify, log=lambda *_: None)
        ans = res.answer
        if t_stt:
            ans.timings = {"voz→texto": t_stt, **ans.timings}
        total = round(time.perf_counter() - t0, 2)
        md = [res.text, ""]
        if ans.citations:
            md += ["**Fuentes**", ""] + [f"- [{c.n}] `{c.source}` · {c.heading}" for c in ans.citations] + [""]
        if res.verified:
            md += [f"**Verificación (Jev)** · {len(res.sentences)} frases · {res.removed} quitadas · "
                   f"{res.flagged} a revisar", ""]
            md += [f"- {ICON[s.decision]} {s.p if s.p is not None else '—'} · {s.text}" for s in res.sentences] + [""]
        elif verify:
            md += ["<sub>Sin JEV_API_KEY: respuesta sin verificar.</sub>", ""]
        steps = " · ".join(f"{k} {v} s" for k, v in ans.timings.items())
        md.append(f"<sub>modo {ans.mode} · {RETRIEVERS.get(retriever, 'bm25')} · {total} s ({steps})</sub>")
        return question, "\n".join(md), ans.audio_path
    except Exception as e:
        return typed or "", f"**Error:** {e}\n\n```\n{traceback.format_exc()[-1500:]}\n```", None


def answer_audio(audio_path, retriever: str, verify: bool, voice: bool):
    """Un audio nuevo inicia una pregunta, sin reutilizar el texto de la respuesta anterior."""
    return answer(audio_path, "", retriever, verify, voice)


def build_tab():
    import gradio as gr

    gr.Markdown("Pregunta **hablando** o escribiendo. Respuesta citada, verificada frase a frase y en voz.")
    with gr.Row():
        mic = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Pregunta por voz")
        with gr.Column():
            q = gr.Textbox(label="Pregunta (o lo que se ha entendido de la voz)",
                           placeholder="¿A qué correo hay que enviar la operativa de Luxemburgo?")
            retr = gr.Radio(list(RETRIEVERS), value=list(RETRIEVERS)[0], label="Buscador")
            with gr.Row():
                ver = gr.Checkbox(value=True, label="Verificar con Jev")
                voz = gr.Checkbox(value=True, label="Responder en voz")
    btn = gr.Button("Preguntar", variant="primary")
    out_md, out_audio = gr.Markdown(), gr.Audio(label="Respuesta en voz", type="filepath")
    btn.click(answer, inputs=[mic, q, retr, ver, voz], outputs=[q, out_md, out_audio])
    # Grabar y subir un archivo comparten el mismo flujo de pregunta nueva.
    mic.stop_recording(answer_audio, inputs=[mic, retr, ver, voz], outputs=[q, out_md, out_audio])
    mic.upload(answer_audio, inputs=[mic, retr, ver, voz], outputs=[q, out_md, out_audio])


def build():
    import gradio as gr

    with gr.Blocks(title="B5T4 · Agente 3 · Preguntas") as demo:
        gr.Markdown("# Preguntas al equipo de Gestión Discrecional")
        build_tab()
    return demo


def main() -> None:
    p = argparse.ArgumentParser(description="Interfaz del agente 3 (RAG) v1")
    p.add_argument("--share", action="store_true")
    p.add_argument("--port", type=int, default=7861)
    a = p.parse_args()
    build().launch(share=a.share, server_port=a.port)


if __name__ == "__main__":
    main()
