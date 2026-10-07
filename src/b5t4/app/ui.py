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


def _opinion(reference: bool = False, video: bool = False):
    """Ejecuta el agente 2 y devuelve (resumen en Markdown, ruta del informe HTML, gráficos PNG, vídeo o None)."""
    import json

    from ..agents.opinion import run

    out = run(reference=reference)
    mp4 = None
    if video:
        from ..agents.opinion.video import make_video

        mp4 = str(make_video(out))
    data = json.loads((out / "cambios.json").read_text(encoding="utf-8"))
    ed = " → ".join(f"{e['label']} ({e['fecha']})" for e in data["ediciones"])
    heads = [c for c in data["cambios"] if c["kind"] == "postura"]
    md = [f"**{ed}**", "", data.get("resumen") or ""]
    md += [f"- **{c['label']}**: {c['before']} → **{c['after']}**" for c in heads]
    md += ["", f"Informe completo: `{out / 'informe.html'}`", "", f"<sub>{data['estadisticas'].get('verified', '')} · "
           f"{data['estadisticas'].get('segundos', {}).get('total', '?')} s</sub>"]
    return "\n".join(md), str(out / "informe.html"), [str(p) for p in sorted(out.glob("*.png"))], mp4


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
            gr.Markdown("Qué ha cambiado entre las dos últimas ediciones de la Opinión Corporativa: informe para clientes, gráficos y JSON.")
            with gr.Row():
                ref = gr.Checkbox(label="Extracción de referencia (sin LLM en la lectura de los PDF)", value=False)
                vid = gr.Checkbox(label="Generar también el vídeo resumen (≈ 2 min de proceso)", value=False)
            b2 = gr.Button("Comparar las dos últimas ediciones", variant="primary")
            o2 = gr.Markdown()
            with gr.Row():
                f2, v2 = gr.File(label="Informe HTML"), gr.Video(label="Vídeo resumen")
            g2 = gr.Gallery(label="Gráficos", columns=3, height="auto")

            def _op(r, v):
                res = _safe(_opinion, r, v)
                return (res, None, [], None) if isinstance(res, str) else res

            b2.click(_op, inputs=[ref, vid], outputs=[o2, f2, g2, v2])
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
