# Integración del agente de onboarding

La rama `codex/onboarding-v2` entrega el agente 1 completo y conserva los puntos de entrada de v1.
Incorpora `main` en `3d6d01b`, incluyendo el agente 3 v0 (BM25, respuesta citada, tiempos y voz).
El agente 2 conserva su listado de ediciones y su aviso de implementación pendiente.
La aplicación completa con las nuevas versiones de los tres agentes requerirá sus correspondientes PR.

## Montaje de la aplicación

`src/b5t4/app/ui.py` monta las tres pestañas. La conversación, los componentes y los callbacks
del onboarding residen en `src/b5t4/app/ui_onboarding.py`; este módulo expone `build_tab()` y
no importa los agentes 2 y 3. Para reutilizarlo:

```python
from b5t4.app import ui_onboarding

with gr.Tab("1 · Onboarding"):
    ui_onboarding.build_tab()
```

Los futuros módulos de interfaz de opinión y preguntas pueden montarse del mismo modo en sus
pestañas. Cada uno debe conservar su propio estado de sesión. Las colas y el estado del onboarding
pertenecen a su ejecución; no hay un briefing global compartido por los tres agentes.
La configuración y los resultados se obtienen de `Settings`; `launch()` permite servir `out/`.
Gradio requiere la versión 6 o posterior, y `uv.lock` fija la versión validada.

## Contratos y archivos compartidos

| Punto de integración | Contrato conservado / cambio |
|---|---|
| `agents/onboarding/__init__.py` | `run(out_root=None, log=print, *, resume=None, report_only=False, brief=None)` devuelve la carpeta de resultados |
| `cli.py` | Añade `onboarding --brief`, `--resume`, `--report-only`; conserva `opinion` y `rag chunks/index/ask/eval` de `main` |
| `config.py`, `config/b5t4.toml`, `.env.example` | Añade modelos de imagen/TTS, voz y presupuesto v2; conserva opciones RAG, verificador y voz local |
| `models/openrouter.py` | Adaptador nuevo para onboarding; no sustituye `llm.py`, `verifier.py` ni `tts.py` |
| `render/schemas.py`, `render/video.py`, `templates/scene.html` | Conserva `Scene`, `Storyboard`, `narrate`, `render` y `make_video`; activa marca y GSAP/D3 únicamente con `layout="onboarding_v2"` |
| `render/report.py` | Conserva Markdown/HTML genérico; los documentos de referencia v2 utilizan `render/onboarding.py` |
| `render/infographic.py` | Añade los componentes de onboarding, manteniendo la entrada del motor existente |
| `app/ui.py` | Montaje común, marca y arranque; onboarding se encapsula en `app/ui_onboarding.py` |
| `pyproject.toml`, `uv.lock` | Dependencias comunes; conserva `snowballstemmer` incorporado por `main` y fija el entorno validado |

El onboarding guarda sus artefactos en `out/onboarding/`; los índices RAG permanecen en `index/`.
Su caché de Jev también reside en `out/onboarding/`. Los datos originales no se modifican.
No se versionan `.env`, corpus, índices, modelos descargados ni informes, imágenes y vídeos generados.
Los logos oficiales y las bibliotecas JS con sus licencias sí son recursos del código.

## Revisión antes de integrar las siguientes ramas

1. Actualizar cada rama desde `main` y resolver los archivos comunes conservando los contratos anteriores.
2. Montar la interfaz de cada agente dentro de su pestaña, manteniendo aislados sus callbacks y sesiones.
3. Ejecutar `uv sync --locked --group dev`, `uv run playwright install chromium` y `uv run pytest`.
4. Probar desde la misma aplicación una conversación de onboarding, una comparación de opiniones y
   una pregunta citada con voz. Esta comprobación conjunta queda pendiente hasta disponer de los tres flujos.
5. Abrir una PR por rama y repetir las comprobaciones tras cada integración. Los commits locales de
   validación no fusionan ni publican trabajo de otros compañeros.

`tests/test_app_integration.py` comprueba las tres pestañas, el paso del briefing desde CLI,
los callbacks existentes de opinión/RAG y las seis composiciones originales de vídeo con Chromium.
La verificación documental y las pruebas con datos reales se documentan en
`VALIDACION_ONBOARDING_V2.md`; sus artefactos privados se conservan localmente.

La revisión de esta entrega pasa 51 pruebas sin corpus; las cinco pruebas de datos se omiten en
ese entorno. Con los datos locales pasan otras cuatro, pero el golden set del RAG requiere resolver
los documentos no legibles de OneDrive. No hay workflows de CI configurados en el repositorio.
