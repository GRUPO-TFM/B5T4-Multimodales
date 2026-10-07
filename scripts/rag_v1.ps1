# Agente 3 (RAG) v1 en Windows. Añade Whisper y EmbeddingGemma 2 SIN tocar pyproject.toml ni uv.lock:
# `uv run --with` los instala en un entorno superpuesto (en caché) solo para estos comandos.
#
#   .\scripts\rag_v1.ps1 ui                    interfaz con micrófono  → http://127.0.0.1:7861
#   .\scripts\rag_v1.ps1 dense                 índice denso EmbeddingGemma 2 (texto + páginas como imagen)
#   .\scripts\rag_v1.ps1 compare [--answers hybrid]   BM25 vs denso vs híbrido con el golden set
#   .\scripts\rag_v1.ps1 voz pregunta.wav      pregunta por voz desde la consola
#   .\scripts\rag_v1.ps1 test                  pruebas
param([Parameter(Position = 0)][string]$cmd = "ui", [Parameter(ValueFromRemainingArguments = $true)]$rest)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$voz = @("--with", "faster-whisper>=1.2")
$emb = @("--with", "sentence-transformers>=6.1.0", "--with", "transformers>=5.19", "--with", "torch>=2.6")

switch ($cmd) {
    "ui"      { uv run @voz @emb python -m b5t4.app.ui_rag @rest }
    "dense"   { uv run @emb python scripts/rag_dense_index.py @rest }
    "compare" { uv run @emb python scripts/rag_compare.py @rest }
    "voz"     { uv run @voz @emb python scripts/rag_voz.py @rest }
    "test"    { uv run pytest tests/test_rag_v1.py @rest }
    default   { Write-Host "Comando desconocido: $cmd (ui | dense | compare | voz | test)"; exit 2 }
}
