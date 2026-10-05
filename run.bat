@echo off
REM Arranque de la interfaz del MVP B5-T4 en Windows. Requiere uv (https://docs.astral.sh/uv/).
cd /d "%~dp0"
uv sync || exit /b 1
uv run playwright install chromium
if not exist models\kokoro-v1.0.onnx uv run python scripts\download_models.py
uv run b5t4 check
uv run b5t4 ui
