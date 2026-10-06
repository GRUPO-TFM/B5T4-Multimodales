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
             "verificacion.json", "fuentes.json", "validacion_video.json", "ejecucion.json",
             "brief.json", "referencia.json", "direccion.json", "guion.json", "infografia.html", "voz.wav",
             "consumo_openrouter.json", "consumo_jev.json", "revision_audio.json", "revision_audio_independiente.json",
             "revision_audio_comparativa.json", "validacion_diseno.json")
    ledger = folder / "consumo_openrouter.json" if folder else None
    if ledger and ledger.is_file():
        usage = json.loads(ledger.read_text(encoding="utf-8"))
        status += f"\n\nOpenRouter: **{usage['accounted_usd']:.3f} / {usage['limit_usd']:.2f} USD** contabilizados."
        if usage.get("uncertain_requests"):
            status += " Incluye reservas de peticiones cuyo coste definitivo aún no está disponible."
    jev = folder / "consumo_jev.json" if folder else None
    if jev and jev.is_file():
        usage = json.loads(jev.read_text(encoding="utf-8"))
        status += f"\n\nJev: **{usage['requests']} peticiones**, {usage['cache_hits']} verificaciones reutilizadas; consumo separado de OpenRouter."
    downloads = [str(folder / name) for name in names if (folder / name).is_file()] if folder else []
    return (status, md.read_text(encoding="utf-8") if md and md.is_file() else "",
            str(image) if image and image.is_file() else None,
            str(video) if video and video.is_file() else None, downloads)


def _load_onboarding(folder: str):
    try:
        path = Path(folder).resolve()
        state = json.loads((path / "ejecucion.json").read_text(encoding="utf-8"))
        label = "Onboarding completo" if state["status"] == "complete" else "Resultados parciales"
        status = f"**{label}.** {state['stage']}\n\nSalida en `{path}`"
        if state.get("error"): status += "\n\nIncidencia: " + state["error"]
        return _onboarding_result(path, status)
    except (OSError, ValueError, KeyError) as exc:
        return f"No se pueden abrir los resultados: {exc}", "", None, None, []


def _onboarding(resume_folder: str = "", report_only: bool = False, brief=None):
    """Progreso por etapas y resultados parciales, sin bloquear la cola de presentación."""
    from ..agents.onboarding import run

    events = queue.Queue()
    lines, folder = [], None

    def worker():
        try:
            result = run(resume=Path(resume_folder) if resume_folder.strip() else None,
                         report_only=report_only, brief=brief, log=lambda msg: events.put(("log", str(msg))))
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


def _brief_message(message, state):
    import gradio as gr
    from ..agents.onboarding.conversation import chat
    try:
        if not message.strip():
            raise ValueError("Describe qué onboarding necesitas")
        state, response = chat(message, state)
        draft = response.draft
        ready = not draft.missing()
        return (state, state["history"], "", draft.role, draft.experience, draft.objective, draft.area,
                draft.duration_seconds/60, "Encargo listo para confirmar." if ready else "Falta concretar: " + ", ".join(draft.missing()),
                gr.update(interactive=ready))
    except Exception as error:
        return state, (state or {}).get("history", []), message, "", "", "", "", 2, str(error), gr.update(interactive=False)


def _personalized(state, role, experience, objective, area, minutes, budget, report_only):
    import gradio as gr
    from ..agents.onboarding.conversation import confirm
    try:
        if state and state.get("confirmed"):
            raise ValueError("Este encargo ya se confirmó. Para cambiarlo, inicia un nuevo encargo.")
        state, brief = confirm(state, role=role, experience=experience, objective=objective,
                               area=area, minutes=minutes, budget=budget)
        for index, result in enumerate(_onboarding(report_only=report_only, brief=brief)):
            # Los eventos de progreso no restauran el estado de un encargo antiguo
            # si el usuario ha comenzado otra conversación mientras se genera.
            yield (state if index == 0 else gr.skip()), (gr.update(interactive=False) if index == 0 else gr.skip()), *result
    except Exception as error:
        yield state, gr.update(interactive=True), str(error), "", None, None, []


def _new_brief():
    import gradio as gr
    from ..agents.onboarding.conversation import new_session
    return new_session(), [], "", "", "Se incorpora al equipo", "", "Gestión Discrecional", 2, "Describe el nuevo encargo.", gr.update(interactive=False)


def _resume_onboarding(folder, report_only=False):
    if not folder.strip():
        yield "Indica la carpeta de una ejecución para reanudarla.", "", None, None, []
        return
    yield from _onboarding(folder, report_only)


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
        from ..render.brand import logo_url
        gr.HTML('<div class="app-brand"><span>GESTIÓN DISCRECIONAL</span><div class="andbank-logo"><img alt="Andbank Private Bankers" src="' + logo_url() + '"></div></div>')
        gr.Markdown("# Onboarding multimodal · Gestión Discrecional\nDe la carpeta de trabajo del equipo a su onboarding: informe, infografía, vídeo y respuestas.")
        with gr.Tab("1 · Onboarding"):
            gr.Markdown("Documento de referencia, infografía y vídeo personalizado de 1 a 5 minutos. Describe el perfil y el objetivo; confirma el encargo para generar las tres piezas con la identidad Andbank.")
            brief_state = gr.State(None)
            chat = gr.Chatbot(label="Preparar la incorporación", height=320)
            message = gr.Textbox(label="Tu encargo", placeholder="Soy analista junior de Alpha. Necesito conocer el proceso semanal, los controles y a quién acudir.", lines=2)
            with gr.Row():
                send = gr.Button("Enviar")
                fresh = gr.Button("Nuevo encargo")
            with gr.Accordion("Resumen del encargo · puedes editarlo", open=True):
                with gr.Row():
                    role = gr.Textbox(label="Puesto")
                    experience = gr.Textbox(label="Experiencia", value="Se incorpora al equipo")
                objective = gr.Textbox(label="Objetivo", lines=3)
                area = gr.Textbox(label="Área de interés", value="Gestión Discrecional")
                minutes = gr.Slider(label="Duración máxima del vídeo (minutos)", minimum=1, maximum=5, value=2, step=.5)
                budget = gr.Number(label="Presupuesto de OpenRouter (USD)", value=5, minimum=.1, maximum=100)
            brief_status = gr.Markdown()
            resume = gr.Textbox(label="Carpeta de resultados para abrir o reanudar (opcional)")
            report_only = gr.Checkbox(label="Generar solo el informe", value=False)
            with gr.Row():
                confirm = gr.Button("Confirmar encargo y generar", variant="primary", interactive=False)
                b1 = gr.Button("Reanudar ejecución")
                load1 = gr.Button("Abrir resultados existentes")
            o1 = gr.Markdown()
            with gr.Row():
                onboarding_image = gr.Image(label="Infografía", type="filepath")
                onboarding_video = gr.Video(label="Vídeo de incorporación")
            onboarding_files = gr.File(label="Descargar resultados", file_count="multiple")
            with gr.Accordion("Informe y fuentes", open=False):
                onboarding_report = gr.Markdown()
            fields = [brief_state, chat, message, role, experience, objective, area, minutes, brief_status, confirm]
            send.click(_brief_message, inputs=[message, brief_state], outputs=fields, concurrency_limit=1)
            message.submit(_brief_message, inputs=[message, brief_state], outputs=fields, concurrency_limit=1)
            fresh.click(_new_brief, outputs=fields)
            confirm.click(_personalized, inputs=[brief_state, role, experience, objective, area, minutes, budget, report_only],
                          outputs=[brief_state, confirm, o1, onboarding_report, onboarding_image, onboarding_video, onboarding_files], concurrency_limit=1)
            b1.click(_resume_onboarding, inputs=[resume, report_only],
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
    import gradio as gr
    theme = gr.themes.Base(primary_hue=gr.themes.colors.red,
                          font=[gr.themes.Font(name) for name in ("Verdana", "Arial", "sans-serif")]).set(
        button_primary_background_fill="#D52B1E", button_primary_background_fill_hover="#762E2F",
        body_background_fill="#FFFFFF", body_text_color="#000000")
    css = (get_settings().templates_dir / "onboarding-v2.css").read_text(encoding="utf-8")
    css += '\n.app-brand{display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid #D52B1E;padding:8px 0}.app-brand>span{font-size:13px;letter-spacing:2px;color:#928B81}'
    build().queue().launch(share=share, allowed_paths=[str(get_settings().out_dir)], theme=theme, css=css)
