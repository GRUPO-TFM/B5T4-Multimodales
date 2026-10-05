"""Capa de modelos de IA: un adaptador por modalidad, cada uno con una interfaz mínima y estable.

  llm.py         texto y JSON validado (OpenRouter) · visión sobre imágenes de páginas
  verifier.py    verificación afirmación-pasaje y cumplimiento (Jev, probabilidad calibrada)
  tts.py         texto → voz (Kokoro, local)
  stt.py         voz → texto (pendiente: faster-whisper)
  embeddings.py  texto → vector (pendiente: multilingual-e5)

Los agentes solo hablan con estas interfaces: cambiar de proveedor no toca la lógica de negocio."""
