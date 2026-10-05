"""
Interfaz (Gradio): tres pestañas, una por agente. Solo presentación: no contiene lógica de negocio,
llama a los agentes y enseña lo que devuelven (HTML, imagen, vídeo, audio).

    uv run b5t4 ui            → http://127.0.0.1:7860
    uv run b5t4 ui --share    → enlace público temporal (útil para enseñar la demo)

Mientras un agente esté «pendiente», su pestaña muestra el mensaje de NotImplementedError en lugar de fallar.
"""
from __future__ import annotations

import traceback


def _safe(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError as e:
        return f"**Pendiente de implementar.** {e}"
    except Exception as e:  # la demo no debe caerse por un error de un agente
        return f"**Error:** {e}\n\n```\n{traceback.format_exc()[-1500:]}\n```"


def _onboarding():
    from ..agents.onboarding import run

    out = run()
    return f"Salida en `{out}`"


def _opinion():
    from ..agents.opinion import list_editions, run

    eds = list_editions()
    head = "Ediciones encontradas:\n\n" + "\n".join(f"- {e.date} · {e.label}" for e in eds) + "\n\n"
    return head + str(_safe(run))


def _ask(question: str, want_voice: bool):
    from ..agents.rag import ask

    res = _safe(ask, question, want_voice)
    if isinstance(res, str):
        return res, None
    cites = "\n".join(f"- [{c.n}] `{c.source}` · {c.heading}" for c in res.citations)
    steps = " · ".join(f"{k} {v} s" for k, v in res.timings.items())
    foot = f"\n\n<sub>modo {res.mode} · {res.seconds} s ({steps})</sub>"
    return f"{res.text}\n\n**Fuentes**\n\n{cites}{foot}" if cites else f"{res.text}{foot}", res.audio_path


def build():
    import gradio as gr

    with gr.Blocks(title="B5T4 · Onboarding multimodal") as demo:
        gr.Markdown("# Onboarding multimodal · Gestión Discrecional\nDe la carpeta de trabajo del equipo a su onboarding: informe, infografía, vídeo y respuestas.")
        with gr.Tab("1 · Onboarding"):
            gr.Markdown("Informe escrito, infografía y vídeo (≤ 2 min) para una persona que se incorpora al equipo.")
            b1, o1 = gr.Button("Generar onboarding", variant="primary"), gr.Markdown()
            b1.click(lambda: _safe(_onboarding), outputs=o1)
        with gr.Tab("2 · Opinión Corporativa"):
            gr.Markdown("Qué ha cambiado entre ediciones de la Opinión Corporativa: informe y vídeo de los cambios.")
            b2, o2 = gr.Button("Comparar ediciones", variant="primary"), gr.Markdown()
            b2.click(lambda: _safe(_opinion), outputs=o2)
        with gr.Tab("3 · Pregunta"):
            gr.Markdown("Pregunta lo que preguntaría cualquier empleado. Respuesta citada, en texto y en voz.")
            q = gr.Textbox(label="Pregunta", placeholder="¿A qué correo hay que enviar la operativa de Luxemburgo?")
            v = gr.Checkbox(label="Responder también en voz", value=True)
            b3 = gr.Button("Preguntar", variant="primary")
            a_txt, a_audio = gr.Markdown(), gr.Audio(label="Respuesta en voz", type="filepath")
            b3.click(_ask, inputs=[q, v], outputs=[a_txt, a_audio])
    return demo


def launch(share: bool = False) -> None:
    build().launch(share=share)
