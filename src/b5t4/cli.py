"""
Línea de comandos. Todo lo que hace la app se puede lanzar también desde aquí (útil para depurar y para la demo).

    uv run b5t4 check                      ¿encuentro la carpeta de datos, las claves y los modelos de voz?
    uv run b5t4 onboarding                 agente 1: informe, infografía y vídeo verificados
    uv run b5t4 onboarding --resume RUTA   reanuda las etapas de una ejecución
    uv run b5t4 opinion                    agente 2: informe de cambios entre las dos últimas Opinión Corporativa
    uv run b5t4 opinion --referencia       agente 2 sin LLM en la lectura (extracción de referencia): para probar
    uv run b5t4 opinion --eval             agente 2: ¿lee bien el LLM los PDF? (frente a la referencia)
    uv run b5t4 opinion --video            agente 2: informe + vídeo resumen de ≤ 2 min en out/opinion/<fecha>/video/
    uv run b5t4 rag chunks                 agente 3: trocea el corpus y enseña estadísticas
    uv run b5t4 rag index                  agente 3: (re)construye el índice en index/ (hacerlo si cambian los datos)
    uv run b5t4 rag ask "¿…?" [--voice]    agente 3: pregunta; respuesta citada (y en voz con --voice)
    uv run b5t4 rag eval [--answers]       agente 3: mide el buscador con el golden set (evals/preguntas_rag.yaml)
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
    import json

    brief = json.loads(Path(args.brief).read_text(encoding="utf-8")) if args.brief else None
    return _run_agent(lambda: run(resume=Path(args.resume) if args.resume else None, report_only=args.report_only, brief=brief))


def cmd_opinion(args) -> int:
    if args.eval:
        from .agents.opinion.evaluate import run_eval

        return _run_agent(lambda: run_eval(use_cache=not args.sin_cache))
    from .agents.opinion import run

    def go():
        out = run(use_cache=not args.sin_cache, reference=args.referencia)
        if args.video:
            from .agents.opinion.video import make_video

            print("6 vídeo")
            print(f"   {make_video(out)}")

    return _run_agent(go)


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
    if args.action == "eval":
        return cmd_rag_eval(args)
    from .agents.rag import ask

    question = " ".join(args.question).strip()
    if not question:
        print('Falta la pregunta: uv run b5t4 rag ask "¿A qué correo hay que enviar la operativa de Luxemburgo?"')
        return 1
    res = ask(question, voice=args.voice)
    print(f"\n{res.text}\n")
    for c in res.citations:
        print(f"  [{c.n}] {c.source} · {c.heading}")
    steps = " · ".join(f"{k} {v} s" for k, v in res.timings.items())
    print(f"\n  modo {res.mode} · {res.seconds} s ({steps})" + (f"\n  audio {res.audio_path}" if res.audio_path else ""))
    return 0


def cmd_rag_eval(args) -> int:
    """
    ¿Encuentra el buscador el documento donde está la respuesta? Para cada pregunta del golden set mira si alguna
    de sus fuentes esperadas sale entre los k primeros fragmentos (recall@k). No necesita LLM ni claves.
    Con --answers, además pregunta al agente completo y enseña la respuesta junto a la esperada.
    """
    import yaml

    from .agents.rag import ask, search
    from .config import ROOT, get_settings

    qs = yaml.safe_load((ROOT / "evals" / "preguntas_rag.yaml").read_text(encoding="utf-8"))
    k = get_settings().top_k
    hits_at = {1: 0, 3: 0, k: 0}
    scored = 0
    for q in qs:
        expected = set(q.get("fuentes") or [])
        ranked = [c.source for _, c in search(q["pregunta"], k)]
        if expected:
            scored += 1
            pos = next((i + 1 for i, src in enumerate(ranked) if src in expected), None)
            for kk in hits_at:
                hits_at[kk] += bool(pos and pos <= kk)
            mark = f"#{pos}" if pos else "--"
        else:
            mark = "n/a"
        print(f"{q['id']}  {mark:>4}  {q['pregunta']}")
        if expected and not (pos and pos <= k):
            print(f"         esperado: {sorted(expected)}\n         top-3:    {ranked[:3]}")
        if args.answers:
            res = ask(q["pregunta"], log=lambda *_: None)
            print(f"         respuesta: {res.text}\n         esperada:  {q['respuesta']}\n")
    print("\n" + " · ".join(f"recall@{kk} {hits_at[kk]}/{scored}" for kk in sorted(hits_at)))
    return 0


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
    onboarding.add_argument("--brief", metavar="JSON", help="encargo personalizado v2 en JSON")
    onboarding.add_argument("--report-only", action="store_true", help="solo informe; v1 permite borrador sin Jev, v2 exige verificación")
    onboarding.set_defaults(fn=cmd_onboarding)
    o = sub.add_parser("opinion", help="agente 2: cambios en la Opinión Corporativa (informe, gráficos, JSON y vídeo)")
    o.add_argument("--referencia", action="store_true", help="usar la extracción de referencia (sin LLM) en el paso 2")
    o.add_argument("--sin-cache", action="store_true", help="volver a leer los PDF con el LLM aunque ya estén extraídos")
    o.add_argument("--eval", action="store_true", help="medir la extracción con LLM frente a la de referencia")
    o.add_argument("--video", action="store_true", help="además del informe, el vídeo resumen (voz Gemini TTS o Kokoro + fotogramas)")
    o.set_defaults(fn=cmd_opinion)
    r = sub.add_parser("rag", help="agente 3: preguntas de empleados")
    r.add_argument("action", choices=["chunks", "index", "ask", "eval"])
    r.add_argument("question", nargs="*", help="pregunta (solo con «ask»)")
    r.add_argument("--voice", action="store_true", help="devolver también la respuesta en audio")
    r.add_argument("--only-contexts", action="store_true", help="«chunks»: solo los documentos de contexto")
    r.add_argument("--answers", action="store_true", help="«eval»: pregunta también al agente (necesita LLM)")
    r.set_defaults(fn=cmd_rag)
    u = sub.add_parser("ui", help="interfaz web (Gradio)")
    u.add_argument("--share", action="store_true", help="enlace público temporal de Gradio (para la demo)")
    u.set_defaults(fn=cmd_ui)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
