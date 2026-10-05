"""MVP B5-T4 · de la carpeta de trabajo de un equipo a su onboarding.

Capas (de abajo arriba):
  config   rutas y claves (config/b5t4.toml + .env)
  corpus   acceso a la carpeta de la empresa: manifiesto, contextos, extracción de texto
  models   adaptadores de IA: LLM y visión, verificador, voz (TTS/STT), embeddings
  render   salidas: informe HTML, infografía, vídeo
  agents   lógica de negocio: onboarding · opinion · rag
  app      interfaz (Gradio) · cli.py: línea de comandos
"""
__version__ = "0.1.0"
