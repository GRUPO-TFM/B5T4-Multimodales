"""
Pregunta por VOZ desde la línea de comandos: audio → Whisper → RAG (con Jev si hay clave) → respuesta en voz.

Uso:  uv sync --extra rag-voz
      uv run python scripts/rag_voz.py pregunta.wav [--buscador hybrid] [--sin-voz]
"""
import argparse

from b5t4.models.stt_whisper import transcribe_timed

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio")
    p.add_argument("--buscador", choices=["bm25", "hybrid"], default="bm25")
    p.add_argument("--sin-voz", action="store_true")
    a = p.parse_args()

    from b5t4.app.ui_rag import _search_fn
    from b5t4.agents.rag.verify import ask_verified

    question, t = transcribe_timed(a.audio)
    print(f"entendido ({t} s): {question}\n")
    r = ask_verified(question, voice=not a.sin_voz, search_fn=_search_fn(a.buscador))
    print(r.text + "\n")
    for c in r.answer.citations:
        print(f"  [{c.n}] {c.source} · {c.heading}")
    print(f"\n  tiempos: voz→texto {t} s · {r.answer.timings}")
    if r.answer.audio_path:
        print(f"  audio: {r.answer.audio_path}")
