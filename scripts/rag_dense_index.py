"""
Construye el índice denso del agente 3 con EmbeddingGemma 2 (texto + páginas de PDF como imagen).

Uso:  uv sync --extra rag-emb
      uv run b5t4 rag index                       # primero el índice BM25 (los fragmentos de texto)
      uv run python scripts/rag_dense_index.py    # [--sin-imagenes]

La primera vez descarga el modelo (~1,5 GB). En CPU tarda unos minutos; se repite solo si cambian los datos.
"""
import argparse

from b5t4.agents.rag.dense import build_dense

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-imagenes", action="store_true", help="indexar solo texto")
    build_dense(with_images=not p.parse_args().sin_imagenes)
