"""
Interfaz (Gradio): tres pestañas, una por agente. Solo presentación: no contiene lógica de negocio,
llama a los agentes y enseña lo que devuelven (HTML, imagen, vídeo, audio).

    uv run b5t4 ui            → http://127.0.0.1:7860
    uv run b5t4 ui --share    → enlace público temporal (útil para enseñar la demo)

Mientras un agente esté «pendiente», su pestaña muestra el mensaje de NotImplementedError en lugar de fallar.
"""
from __future__ import annotations

import traceback
import json
import queue
import threading
from pathlib import Path


def _safe(fn, *args):
    try:
        return fn(*args)
    except NotImplementedError as e:
        return f"**Pendiente de implementar.** {e}"
    except Exception as e:  # la demo no debe caerse por un error de un agente
        return f"**Error:** {e}\n\n```\n{traceback.format_exc()[-1500:]}\n```"


def _onboarding_result(folder: Path | None, status: str):
    md = folder / "informe.md" if folder else None
    image = folder / "infografia.png" if folder else None
    video = folder / "video.mp4" if folder else None
    names = ("informe.html", "informe.md", "infografia.png", "video.mp4", "storyboard.json",
             "verificacion.json", "fuentes.json", "validacion_video.json", "ejecucion.json")
    downloads = [str(folder / name) for name in names if (folder / name).is_file()] if folder else []
    return (status, md.read_text(encoding="utf-8") if md and md.is_file() else "",
            str(image) if image and image.is_file() else None,
            str(video) if video and video.is_file() else None, downloads)


def _load_onboarding(folder: str):
    try:
        path = Path(folder).resolve()
        state = json.loads((path / "ejecucion.json").read_text(encoding="utf-8"))
        label = "Onboarding completo" if state["status"] == "complete" else "Resultados parciales"
        return _onboarding_result(path, f"**{label}.** {state['stage']}\n\nSalida en `{path}`")
    except (OSError, ValueError, KeyError) as exc:
        return f"No se pueden abrir los resultados: {exc}", "", None, None, []


def _onboarding(resume_folder: str = "", report_only: bool = False):
    """Progreso por etapas y resultados parciales, sin bloquear la cola de presentación."""
    from ..agents.onboarding import run

    events = queue.Queue()
    lines, folder = [], None

    def worker():
        try:
            result = run(resume=Path(resume_folder) if resume_folder.strip() else None,
                         report_only=report_only, log=lambda msg: events.put(("log", str(msg))))
            events.put(("done", result))
        except Exception as exc:
            events.put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()
    yield "Preparando el onboarding…", "", None, None, []
    while True:
        try:
            kind, value = events.get(timeout=1)
        except queue.Empty:
            continue
        if kind == "log":
            lines.append(value)
            if value.startswith("Salida: "):
                folder = Path(value.removeprefix("Salida: "))
            yield "**En curso**\n\n```text\n" + "\n".join(lines[-12:]) + "\n```", "", None, None, []
            continue
        if kind == "done":
            folder = value
        status = f"**Completado.** Salida en `{folder}`" if kind == "done" else f"**No se ha completado:** {value}"
        if kind == "error" and folder:
            status += f"\n\nPuedes reanudar desde `{folder}`. Las etapas terminadas están guardadas."
        yield _onboarding_result(folder, status)
        break


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
    cites = "\n".join(f"[{c.n}] `{c.source}` · {c.heading}" for c in res.citations)
    return f"{res.text}\n\n{cites}", res.audio_path


def build():
    import gradio as gr

    with gr.Blocks(title="B5T4 · Onboarding multimodal") as demo:
        gr.Markdown("# Onboarding multimodal · Gestión Discrecional\nDe la carpeta de trabajo del equipo a su onboarding: informe, infografía, vídeo y respuestas.")
        with gr.Tab("1 · Onboarding"):
            gr.Markdown("Informe escrito, infografía y vídeo (≤ 2 min) para una persona que se incorpora al equipo.")
            resume = gr.Textbox(label="Carpeta de resultados para abrir o reanudar (opcional)")
            report_only = gr.Checkbox(label="Generar solo el informe", value=False)
            with gr.Row():
                b1 = gr.Button("Generar / reanudar onboarding", variant="primary")
                load1 = gr.Button("Abrir resultados existentes")
            o1 = gr.Markdown()
            with gr.Row():
                onboarding_image = gr.Image(label="Infografía", type="filepath")
                onboarding_video = gr.Video(label="Vídeo de incorporación")
            onboarding_files = gr.File(label="Descargar resultados", file_count="multiple")
            with gr.Accordion("Informe y fuentes", open=False):
                onboarding_report = gr.Markdown()
            b1.click(_onboarding, inputs=[resume, report_only],
                     outputs=[o1, onboarding_report, onboarding_image, onboarding_video, onboarding_files],
                     concurrency_limit=1)
            load1.click(_load_onboarding, inputs=resume,
                        outputs=[o1, onboarding_report, onboarding_image, onboarding_video, onboarding_files])
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
    build().queue().launch(share=share, allowed_paths=[str(get_settings().out_dir)])
