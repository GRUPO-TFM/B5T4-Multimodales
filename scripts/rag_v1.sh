#!/usr/bin/env bash
# Agente 3 (RAG) v1 en macOS / Linux. Mismo uso que scripts/rag_v1.ps1:
#   ./scripts/rag_v1.sh ui | dense | compare [--answers hybrid] | voz pregunta.wav | test
# Whisper y EmbeddingGemma 2 se añaden con `uv run --with` (sin tocar pyproject.toml ni uv.lock).
set -euo pipefail
cd "$(dirname "$0")/.."
cmd="${1:-ui}"; shift || true
VOZ=(--with "faster-whisper>=1.2")
EMB=(--with "sentence-transformers>=6.1.0" --with "transformers>=5.19" --with "torch>=2.6")
case "$cmd" in
  ui)      uv run "${VOZ[@]}" "${EMB[@]}" python -m b5t4.app.ui_rag "$@" ;;
  dense)   uv run "${EMB[@]}" python scripts/rag_dense_index.py "$@" ;;
  compare) uv run "${EMB[@]}" python scripts/rag_compare.py "$@" ;;
  voz)     uv run "${VOZ[@]}" "${EMB[@]}" python scripts/rag_voz.py "$@" ;;
  test)    uv run pytest tests/test_rag_v1.py "$@" ;;
  *)       echo "Comando desconocido: $cmd (ui | dense | compare | voz | test)"; exit 2 ;;
esac
