# Registro de decisiones

Una línea por decisión: qué se decidió, por qué y qué alternativa se descartó.

| # | Fecha | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|---|
| 1 | 05-oct-2026 | Cambio de MVP: de MarketBrief (brief de mercado desde redes) a un **MVP de onboarding** (onboarding desde la carpeta de trabajo de un equipo) | Problema real y medible (incorporar a alguien a un equipo con 1.000+ ficheros); datos propios ricos; tres modalidades de salida con sentido | MarketBrief: ingesta de redes frágil y diferenciación baja |
| 2 | 05-oct-2026 | Los datos **no están en el repo**: `B5T4_DATA_DIR` apunta a la copia estructurada `Tarea MIAX` | Información interna del banco; el repo solo contiene código | Copiar los datos al repo |
| 3 | 05-oct-2026 | Copia estructurada con **manifiesto** y **contextos con plantilla fija de 11 secciones** | Retrieval barato (filtrar por metadatos antes de buscar) y fragmentos con sentido completo | Indexar la carpeta original tal cual |
| 4 | 05-oct-2026 | **OpenRouter** con modelos baratos por defecto; modelo configurable | Una clave, cualquier modelo, coste mínimo | APIs directas de cada proveedor |
| 5 | 02-oct-2026 | **Vídeo determinista** (storyboard → HTML/CSS → Playwright → ffmpeg) con voz **Kokoro** local | Cifras y nombres exactos; gratis; probado de extremo a extremo (prototipo Micron, 37 s en ~90 s de CPU) | Modelos generativos de vídeo (inventan texto, caros, lentos) |
| 6 | 02-oct-2026 | **Jev** como verificador afirmación-pasaje y puerta de cumplimiento | Banco de pruebas propio: 11/12 (Brier 0,071) y 10/10 (Brier 0,017) | Juez LLM (más caro, peor calibrado) |
| 7 | 05-oct-2026 | **Gradio** para la interfaz | Componentes nativos de audio, vídeo y chat; `share=True` para la demo | Streamlit |
| 8 | 05-oct-2026 | Agente 2: **comparación determinista** en Python; el LLM solo extrae y explica | Un cambio de recomendación no puede inventarse | Pedir al LLM «compara estas dos ediciones» |
| 9 | 05-oct-2026 | Agente 3: **retrieval híbrido** BM25 + embeddings multilingües, con filtros del manifiesto | Preguntas con nombres, correos y siglas | Solo embeddings |
| 10 | 05-oct-2026 | Estructura `src/` con capas `corpus · models · render · agents · app`; un agente por carpeta | Separación de capas pedida en el enunciado (4.4); trabajo en paralelo del equipo sin conflictos | Un único script por agente |
| 11 | 07-oct-2026 | Enlace público con **ngrok dentro del proceso** (`b5t4 ui --ngrok`, SDK `ngrok` de Python) y contraseña opcional `B5T4_UI_AUTH` | Un comando y una línea en `.env`; sin instalar ni actualizar el programa `ngrok`; dirección fija por cuenta; el túnel se cierra con la interfaz | Programa `ngrok` aparte (instalación por máquina, versión mínima exigida por la cuenta, túnel que sobrevive a la interfaz). `--share` de Gradio se mantiene como alternativa sin cuenta |
| — | pendiente | Copia **anonimizada** de la carpeta (`data/sample/`) para que el profesor ejecute la demo | La demo debe funcionar sin acceso a datos reales | — |
| — | pendiente | Modelo de embeddings definitivo (propuesta: `intfloat/multilingual-e5-small`) | Se mide con el golden set | — |
