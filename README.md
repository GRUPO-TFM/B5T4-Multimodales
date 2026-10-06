# B5T4 · Onboarding multimodal

**De la carpeta de trabajo de un equipo a su onboarding.** MVP del Taller B5-T4 (MIAX 14, Instituto BME).

Un equipo de gestión de carteras tiene escrito casi todo lo que un empleado nuevo necesita saber. Está repartido
en más de mil ficheros: manuales de sección, maestros Excel, informes, correos, PDF corporativos y plantillas.
El MVP lee esa carpeta y lo convierte en tres productos:

| # | Agente | Qué entrega | Modalidades |
|---|---|---|---|
| 1 | **Onboarding** | Conversación guiada, documento completo de referencia, infografía y **vídeo personalizado de 1 a 5 min** | conversación → investigación · informe HTML · diagramas · ilustración · voz · vídeo |
| 2 | **Opinión Corporativa** | Informe y **vídeo de los cambios** en la visión de la casa entre ediciones (p. ej. el bono de EE.UU. a 10 años pasa de infraponderar a sobreponderar) | PDF (texto e imagen) → visión → informe · voz · vídeo |
| 3 | **Preguntas** | Un agente al que cualquier empleado pregunta: *¿a qué correo va la operativa de Luxemburgo?* Responde **citando la fuente**, en **texto y en voz** | voz/texto → recuperación híbrida → texto · voz |

Caso real: la carpeta del equipo de **Gestión Discrecional de Andbank España** (1.185 ficheros, 7 secciones de
cartera, 17 personas).

> **Onboarding v2 (7-oct-2026):** conversación y confirmación del encargo, capítulos adaptados al perfil,
> revisiones documentales/editoriales/audiovisuales, marca Andbank y presupuesto por ejecución.
> Uso, contratos y límites: [docs/ONBOARDING_V2.md](docs/ONBOARDING_V2.md).
> Validación real: vídeos de 112,04 y 278,98 s, 47 pruebas y presupuesto verificado.
> Evidencia y ejemplos: [docs/VALIDACION_ONBOARDING_V2.md](docs/VALIDACION_ONBOARDING_V2.md).
> V1 se conserva en `codex/onboarding-completo`, commit `95fe4c5`, y sigue disponible sin `--brief`.
> Su validación: [docs/VALIDACION_ONBOARDING.md](docs/VALIDACION_ONBOARDING.md).
> Los agentes 2 y 3 mantienen su estado inicial.

---

## Cómo funciona

```mermaid
flowchart LR
    DATA[("Carpeta de la empresa<br/>manifiesto + 20 contextos<br/>+ 1.185 ficheros")] --> CORPUS["corpus<br/>leer · filtrar · trocear"]
    CORPUS --> A1["Agente 1<br/>Onboarding"]
    CORPUS --> A2["Agente 2<br/>Opinión Corporativa"]
    CORPUS --> A3["Agente 3<br/>Preguntas (RAG)"]
    A1 --> OUT1["referencia personalizada · infografía · vídeo 1–5 min"]
    A2 --> OUT2["informe de cambios · vídeo"]
    A3 --> OUT3["respuesta citada · voz"]
    MODELS["models<br/>Gemini texto/visión/imagen/TTS · Jev<br/>Kokoro v1 · Whisper · embeddings"] -.-> A1
    MODELS -.-> A2
    MODELS -.-> A3
```

Tres ideas sostienen el diseño (detalle en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)):

1. **La carpeta de datos está preparada para agentes.** Cada carpeta tiene un `00_CONTEXTO.md` con la misma
   plantilla de 11 secciones (Qué es · Responsables · Objetivos · …). Hay además un `00_MANIFIESTO.csv` con el
   estado de cada fichero (vigente, archivo o duplicado). Los agentes filtran antes de buscar y trocean por
   sección, no por número de caracteres.
2. **El modelo propone; los contratos y verificaciones controlan la entrega.** Los LLM seleccionan, redactan
   y dirigen la narrativa. Jev comprueba el respaldo documental; otras llamadas revisan la calidad editorial
   y visual. El código controla marca, presupuesto, persistencia y composición.
3. **El storyboard y la voz medida fijan el montaje.** Gemini TTS produce la voz de v2; Kokoro mantiene v1.
   Chromium dibuja componentes con GSAP/D3 y ffmpeg monta el MP4. Textos, cifras, logos y diagramas se dibujan
   por código; las ilustraciones generadas son conceptuales y se revisan.

---

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/) y Python 3.12. Windows, macOS o Linux.

```powershell
git clone https://github.com/GRUPO-TFM/B5T4-Multimodales.git; cd B5T4-Multimodales
copy .env.example .env          # rellena B5T4_DATA_DIR, OPENROUTER_API_KEY y JEV_API_KEY
uv sync                          # crea .venv con todas las dependencias
uv run playwright install chromium
uv run python scripts/download_models.py     # voz Kokoro, ~350 MB, una sola vez
uv run b5t4 check           # comprueba datos, claves y modelos
uv run b5t4 ui              # interfaz en http://127.0.0.1:7860
```

En Windows, `run.bat` hace todo lo anterior salvo el `.env`.

### A qué carpeta apunta

El repo **no contiene los datos**. Lee la carpeta indicada en `B5T4_DATA_DIR` (en `.env`) o, si no está, en
`data_dir` de `config/b5t4.toml`. Por defecto es:

```
C:/Users/javie/OneDrive/04. Andbank Work/Tarea MIAX
```

Cada miembro del equipo pone su ruta en su `.env`. Para ejecutar la demo sin acceso a los datos reales habrá una
copia anonimizada en `data/sample/` (pendiente).

### Comandos

| Comando | Qué hace | Estado |
|---|---|---|
| `uv run b5t4 check` | Comprueba la carpeta de datos, el manifiesto, los contextos, las claves, la voz y ffmpeg | ✅ |
| `uv run b5t4 onboarding --brief "encargo.json"` | V2 personalizado: referencia, infografía y vídeo de 1–5 min | Implementado |
| `uv run b5t4 onboarding` | V1. Informe verificado, infografía y vídeo ≤ 120 s | Compatible |
| `uv run b5t4 onboarding --report-only` | Genera el informe; permite borrador si no hay Jev | Implementado |
| `uv run b5t4 onboarding --resume "out/onboarding/<ejecución>"` | Reutiliza las etapas terminadas si las fuentes no cambiaron | Implementado |
| `uv run b5t4 opinion` | Agente 2. Hoy lista las ediciones de la Opinión Corporativa | 🟡 paso 1 de 5 |
| `uv run b5t4 rag chunks` | Agente 3. Trocea el corpus (~2.700 fragmentos con metadatos) | ✅ |
| `uv run b5t4 rag index` / `rag ask "…"` | Agente 3. Índice y respuesta | ⏳ |
| `uv run b5t4 ui [--share]` | Interfaz Gradio con las tres pestañas | ✅ (muestra «pendiente» donde corresponde) |
| `uv run pytest` | Pruebas de datos, fuentes, verificación, reanudación, interfaz y render | Incluye regresiones del onboarding |

---

## Estructura del repositorio

```
├── README.md                    este documento
├── pyproject.toml · uv.lock     dependencias (uv)
├── .env.example                 plantilla de claves y ruta de datos (.env no se sube)
├── run.bat · run.sh             arranque en un paso
├── config/
│   └── b5t4.toml           rutas, modelos, parámetros de vídeo y RAG
├── docs/
│   ├── ARQUITECTURA.md          capas, diagramas de los tres agentes, modalidades, principios
│   ├── DECISIONES.md            registro de decisiones
│   └── PLAN.md                  reparto, calendario hasta el 8-oct y guion de la demo
├── src/b5t4/
│   ├── config.py                configuración (toml + .env)
│   ├── cli.py                   línea de comandos «b5t4 …»
│   ├── corpus/                  CAPA DE DATOS: manifest.py · contexts.py · extract.py
│   ├── models/                  CAPA DE IA: openrouter.py (multimodal/presupuesto) · llm.py · verifier.py · tts.py
│   │                            · stt.py · embeddings.py (pendientes)
│   ├── render/                  CAPA DE SALIDA: report.py · video.py · infographic.py · templates/
│   ├── agents/                  LÓGICA DE NEGOCIO, un agente por carpeta
│   │   ├── onboarding/          agente 1
│   │   ├── opinion/             agente 2
│   │   └── rag/                 agente 3: index.py · answer.py
│   └── app/ui.py                CAPA DE INTERFAZ (Gradio)
├── evals/preguntas_rag.yaml     golden set del agente 3 (15 preguntas con fuente; 1 trampa)
├── notebooks/                   exploración del corpus
├── scripts/                     download_models.py · jev_benchmark.py
├── tests/                       pruebas (pytest)
└── data/ · models/ · out/ · index/   fuera de Git (datos, voz, salidas, índice)
```

---

## Costes y privacidad

- **Coste por ejecución v2:** presupuesto inicial de 5 USD en OpenRouter para texto, revisiones, ilustraciones
  y voz. Reserva antes de llamar y registro del coste comunicado. Jev se contabiliza por separado.
  Chromium y ffmpeg funcionan localmente. V1 conserva su voz local.
- **Datos:** el corpus y los artefactos se guardan localmente y quedan fuera de Git. La redacción envía los
  fragmentos seleccionados a OpenRouter; la verificación envía afirmaciones y pasajes a Jev/TypeSafe.
  En v2 la síntesis de voz también utiliza OpenRouter; la composición y el montaje se ejecutan localmente.
  El `golden set` contiene correos internos de
  mesas, así que el repositorio debe ser **privado**.

## Equipo

Organización [GRUPO-TFM](https://github.com/GRUPO-TFM) · Taller B5-T4 · MIAX 14. Repositorio privado
`GRUPO-TFM/B5T4-Multimodales`. Reparto de trabajo y reglas del equipo en [docs/PLAN.md](docs/PLAN.md).
