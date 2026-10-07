#!/usr/bin/env bash
# Arranque de la interfaz del MVP B5-T4 en macOS / Linux. Requiere uv (https://docs.astral.sh/uv/).
set -euo pipefail
cd "$(dirname "$0")"
uv sync
uv run playwright install chromium
[ -f models/kokoro-v1.0.onnx ] || uv run python scripts/download_models.py
uv run b5t4 check
# Los argumentos pasan a la interfaz: «./run.sh --ngrok» abre además el enlace público.
uv run b5t4 ui "$@"
