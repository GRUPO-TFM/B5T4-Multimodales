"""
Línea de comandos. Todo lo que hace la app se puede lanzar también desde aquí (útil para depurar y para la demo).

    uv run b5t4 check                      ¿encuentro la carpeta de datos, las claves y los modelos de voz?
    uv run b5t4 onboarding                 agente 1: informe, infografía y vídeo verificados
    uv run b5t4 onboarding --resume RUTA   reanuda las etapas de una ejecución
    uv run b5t4 opinion                    agente 2 (hoy: lista las ediciones y se detiene)
    uv run b5t4 rag chunks                 agente 3: trocea el corpus y enseña estadísticas
    uv run b5t4 rag ask "¿…?"              agente 3: pregunta (pendiente)
    uv run b5t4 ui                         interfaz web (Gradio)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter


def _ok(flag: bool) -> str:
    return "OK " if flag else "-- "


def cmd_check(_args) -> int:
    from .config import CONFIG_FILE, ROOT, get_settings
    from .corpus import load_contexts, load_manifest, summary

    s = get_settings()
    print(f"repo             {ROOT}")
    print(f"configuración    {CONFIG_FILE} ({'existe' if CONFIG_FILE.exists() else 'NO existe'})")
    print(f"carpeta de datos {s.data_dir}")
    if not s.data_dir.exists():
        print("\nNo encuentro la carpeta de datos. Pon la ruta en .env (B5T4_DATA_DIR=...) o en config/b5t4.toml.")
        return 1
    files = load_manifest(s)
    sm = summary(files)
    print(f"{_ok(True)}manifiesto       {sm['ficheros']} ficheros · {sm['vigentes']} vigentes · {sm['contextos']} contextos")
    print(f"                 por estado: {sm['por_estado']}")
    if sm["faltan_en_disco"]:
        print(f"!! faltan en disco ({len(sm['faltan_en_disco'])}+): {sm['faltan_en_disco'][:5]}")
    docs = load_contexts(s)
    secs = Counter(len(d.sections) for d in docs)
    print(f"{_ok(bool(docs))}contextos        {len(docs)} documentos; secciones por documento: {dict(secs)}")
    print(f"{_ok(s.opinion_path.exists())}opinión          {s.opinion_path}  ({len(list(s.opinion_path.glob('*.pdf'))) if s.opinion_path.exists() else 0} PDF)")
    print(f"{_ok(s.has_llm)}OPENROUTER_API_KEY   modelos: main={s.model_main} · cheap={s.model_cheap} · vision={s.model_vision}")
    print(f"{_ok(s.has_verifier)}JEV_API_KEY          (opcional: verificación y cumplimiento)")
    voice_ok = (s.models_dir / "kokoro-v1.0.onnx").exists() and (s.models_dir / "voices-v1.0.bin").exists()
    print(f"{_ok(voice_ok)}voz Kokoro       {s.models_dir}  {'' if voice_ok else '→ uv run python scripts/download_models.py'}")
    ff = shutil.which("ffmpeg")
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    print(f"{_ok(bool(ff))}ffmpeg           {ff or 'no encontrado'}")
    return 0


def cmd_onboarding(args) -> int:
    from .agents.onboarding import run
    from pathlib import Path

    return _run_agent(lambda: run(resume=Path(args.resume) if args.resume else None, report_only=args.report_only))


def cmd_opinion(_args) -> int:
    from .agents.opinion import run

    return _run_agent(run)


def cmd_rag(args) -> int:
    if args.action == "chunks":
        from .agents.rag import build_chunks

        chunks = build_chunks(include_documents=not args.only_contexts)
        by_folder = Counter(c.folder for c in chunks)
        words = [len(c.text.split()) for c in chunks]
        print(f"{len(chunks)} fragmentos · {sum(words):,} palabras · media {sum(words) / max(1, len(words)):.0f} palabras")
        for k, v in sorted(by_folder.items()):
            print(f"  {k:<42} {v}")
        return 0
    if args.action == "index":
        from .agents.rag import build_index

        return _run_agent(build_index)
    from .agents.rag import ask

    return _run_agent(lambda: print(ask(" ".join(args.question), voice=args.voice).model_dump_json(indent=2)))


def cmd_ui(args) -> int:
    from .app.ui import launch

    launch(share=args.share)
    return 0


def _run_agent(fn) -> int:
    try:
        fn()
        return 0
    except NotImplementedError as e:
        print(f"\n[pendiente] {e}")
        return 2


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="b5t4", description="MVP B5-T4 · onboarding, opinión corporativa y preguntas sobre la carpeta del equipo")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="comprueba datos, claves y modelos").set_defaults(fn=cmd_check)
    onboarding = sub.add_parser("onboarding", help="agente 1: informe + infografía + vídeo de onboarding")
    onboarding.add_argument("--resume", metavar="CARPETA", help="reanudar una ejecución conservando las etapas terminadas")
    onboarding.add_argument("--report-only", action="store_true", help="generar solo el informe; permite un borrador si no hay verificador")
    onboarding.set_defaults(fn=cmd_onboarding)
    sub.add_parser("opinion", help="agente 2: cambios en la Opinión Corporativa").set_defaults(fn=cmd_opinion)
    r = sub.add_parser("rag", help="agente 3: preguntas de empleados")
    r.add_argument("action", choices=["chunks", "index", "ask"])
    r.add_argument("question", nargs="*", help="pregunta (solo con «ask»)")
    r.add_argument("--voice", action="store_true", help="devolver también la respuesta en audio")
    r.add_argument("--only-contexts", action="store_true", help="«chunks»: solo los documentos de contexto")
    r.set_defaults(fn=cmd_rag)
    u = sub.add_parser("ui", help="interfaz web (Gradio)")
    u.add_argument("--share", action="store_true", help="enlace público temporal de Gradio (para la demo)")
    u.set_defaults(fn=cmd_ui)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
