"""
Interfaz (Gradio): tres pestañas, una por agente. Solo presentación: no contiene lógica de negocio,
llama a los agentes y enseña lo que devuelven (HTML, imagen, vídeo, audio).

    uv run b5t4 ui            → http://127.0.0.1:7860
    uv run b5t4 ui --share    → enlace público temporal (útil para enseñar la demo)

Mientras un agente esté «pendiente», su pestaña muestra el mensaje de NotImplementedError en lugar de fallar.
"""
from __future__ import annotations

import traceback
# Compatibilidad con los callbacks de apertura/generación usados por v1.
from .ui_onboarding import (
    build_tab as build_onboarding_tab,
    _onboarding,
    _load_onboarding,
)


def _safe(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError as e:
        return f"**Pendiente de implementar.** {e}"
    except Exception as e:  # la demo no debe caerse por un error de un agente
        return f"**Error:** {e}\n\n```\n{traceback.format_exc()[-1500:]}\n```"


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
        from ..render.brand import logo_url
        gr.HTML('<div class="app-brand"><span>GESTIÓN DISCRECIONAL</span><div class="andbank-logo"><img alt="Andbank Private Bankers" src="' + logo_url() + '"></div></div>')
        gr.Markdown("# Onboarding multimodal · Gestión Discrecional\nDe la carpeta de trabajo del equipo a su onboarding: informe, infografía, vídeo y respuestas.")
        with gr.Tab("1 · Onboarding"):
            build_onboarding_tab()
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
    from ..config import get_settings
    import gradio as gr
    theme = gr.themes.Base(primary_hue=gr.themes.colors.red,
                          font=[gr.themes.Font(name) for name in ("Verdana", "Arial", "sans-serif")]).set(
        button_primary_background_fill="#D52B1E", button_primary_background_fill_hover="#762E2F",
        body_background_fill="#FFFFFF", body_text_color="#000000")
    css = (get_settings().templates_dir / "onboarding-v2.css").read_text(encoding="utf-8")
    css += '\n.app-brand{display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid #D52B1E;padding:8px 0}.app-brand>span{font-size:13px;letter-spacing:2px;color:#928B81}'
    build().queue().launch(share=share, allowed_paths=[str(get_settings().out_dir)], theme=theme, css=css)
