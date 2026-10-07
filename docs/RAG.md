# Agente 3 · Preguntas de empleados (RAG) — v1

Un empleado pregunta, **hablando o escribiendo**, lo que preguntaría a un compañero («¿a qué correo va la
operativa de Luxemburgo?»). El agente busca en la carpeta del equipo, responde **citando la fuente**, **verifica
cada frase** contra lo que cita y contesta también **en voz**.

## 1. Flujo y modelos

```mermaid
flowchart LR
    MIC["🎤 pregunta hablada"] --> STT["Whisper small<br/>(faster-whisper, local)"]
    TXT["⌨️ pregunta escrita"] --> Q
    STT --> Q["pregunta"]
    Q --> BM25["BM25<br/>palabras exactas"]
    Q --> EMB["EmbeddingGemma 2<br/>(texto e imagen, local)"]
    IDX[("índice local<br/>~2.700 fragmentos de texto<br/>+ páginas de PDF como imagen")] --> BM25
    IDX --> EMB
    BM25 --> RRF["fusión RRF"]
    EMB --> RRF
    RRF --> LLM["Gemini Flash (OpenRouter)<br/>respuesta con citas [n]<br/>o «No consta»"]
    LLM --> JEV{"Jev: ¿cada frase<br/>respaldada por su cita?"}
    JEV -->|"≥ 0,80"| OK["se publica"]
    JEV -->|"0,30-0,80"| WARN["⚠️ a revisar"]
    JEV -->|"< 0,30"| DEL["se quita"]
    OK --> OUT["respuesta en texto<br/>+ fuentes"]
    WARN --> OUT
    OUT --> TTS["Kokoro (local)<br/>respuesta en voz"]
```

| Paso | Modalidad | Modelo | Dónde corre | Fichero |
|---|---|---|---|---|
| Voz → texto | audio → texto | Whisper `small` (faster-whisper, int8) | local, CPU | `models/stt_whisper.py` |
| Búsqueda léxica | texto | BM25 propio (Okapi, k1 = 1,4, b = 0,75) + raíz en español | local | `agents/rag/index.py` |
| Búsqueda semántica | texto **e imagen** | EmbeddingGemma 2 (Google, 6-oct-2026, Apache 2.0), 256 d | local, CPU | `models/embed_gemma.py`, `agents/rag/dense.py` |
| Fusión | — | Reciprocal Rank Fusion (K = 60) | local | `agents/rag/hybrid.py` |
| Respuesta | texto → texto | Gemini Flash vía OpenRouter, temperatura 0, JSON validado | nube | `agents/rag/answer.py` |
| Verificación | texto × texto | Jev (TypeSafe), probabilidad calibrada | nube | `agents/rag/verify.py` |
| Voz | texto → audio | Kokoro (ONNX) | local, CPU | `models/tts.py` |

Son **cinco modelos especializados encadenados** (Whisper → EmbeddingGemma 2 → LLM → Jev → Kokoro), cada uno en
lo que hace mejor, y cuatro modalidades (audio, texto, imagen de página, audio de salida).

### Por qué la búsqueda multimodal
Las páginas de los PDF de la Opinión Corporativa se indexan también **como imagen**. EmbeddingGemma 2 pone texto e
imagen en el mismo espacio, así que una pregunta («¿qué opina la casa del bono a 10 años de EE.UU.?») puede encontrar
la página por la **tabla o el gráfico** que contiene, aunque su texto extraído sea pobre. Al LLM se le pasa el texto
de esa página y la cita aparece como «p. N (imagen)».

## 2. Cómo se ejecuta

Requisitos: lo de siempre (`uv sync`, `.env` con `B5T4_DATA_DIR` y `OPENROUTER_API_KEY`, `uv run b5t4 rag index`).
`JEV_API_KEY` es opcional: sin ella la respuesta sale sin verificar y la interfaz lo dice.

Whisper y EmbeddingGemma 2 **no se añaden a `pyproject.toml`** a propósito: `transformers` 5.19 y `faster-whisper`
obligan a bajar `huggingface-hub` (2.1 → 1.33) para todo el proyecto. Los scripts los cargan con `uv run --with`, en
un entorno superpuesto que no toca el del resto del equipo.

```powershell
.\scripts\rag_v1.ps1 dense                    # una vez: índice denso (descarga ~1,5 GB la primera vez)
.\scripts\rag_v1.ps1 compare                  # BM25 vs denso vs híbrido con el golden set
.\scripts\rag_v1.ps1 compare --answers hybrid # + respuestas completas (gasta LLM)
.\scripts\rag_v1.ps1 ui                       # interfaz con micrófono → http://127.0.0.1:7861
.\scripts\rag_v1.ps1 voz pregunta.wav         # pregunta por voz desde la consola
```
En macOS / Linux, lo mismo con `./scripts/rag_v1.sh`.

## 3. Resultados

Golden set: `evals/preguntas_rag.yaml`, 15 preguntas (14 con fuente esperada + 1 trampa sin respuesta).
Recall@k = de las 14, en cuántas sale una fuente correcta entre los k primeros fragmentos.

| Buscador | recall@1 | recall@3 | recall@8 | latencia de búsqueda |
|---|---|---|---|---|
| BM25 (v0) | 5/14 | 12/14 | 14/14 | 0,37 s (medido 7-oct) |
| Denso (EmbeddingGemma 2) | _pendiente_ | | | |
| Híbrido (RRF) | _pendiente_ | | | |

Tiempos de una pregunta completa (7-oct-2026, PC de Javi, CPU; v0 con BM25):

| Paso | Tiempo |
|---|---|
| Voz → texto (Whisper) | _pendiente_ |
| Búsqueda | 0,37 s |
| LLM (4.296 tokens de entrada → 530 de salida) | 6,1 s |
| Jev | _pendiente_ |
| Voz (Kokoro) | 8,3 s |
| **Total** | **14,8 s** |

El cuello de botella es la **síntesis de voz en CPU**, no el LLM. Mejora posible: sintetizar por frases y empezar
a reproducir la primera mientras se generan las demás.

**Coste por pregunta:** unos 4.300 tokens de entrada y 500 de salida en Gemini Flash; del orden de una fracción
de céntimo (estimación con el precio publicado, no factura medida). Whisper, embeddings y voz: 0 €, en local.

### Ejemplo de por qué hace falta verificar
En la prueba de Luxemburgo el LLM añadió el correo concreto de un banquero, mientras que la regla del documento
dice «con copia al banquero del cliente», sin nombre. Es justo el tipo de dato de más que Jev marca o quita.

## 4. Decisiones y parámetros (y por qué se cuestionan)

| Parámetro | Valor | Estado |
|---|---|---|
| BM25 `k1`, `b` | 1,4 · 0,75 | valores de manual; sin ajustar |
| `CONTEXT_BOOST` | ×1,15 a los `00_CONTEXTO.md` | arbitrario; candidato a explicar el 5/14 en primera posición |
| `top_k` | 8 | recall@3 ya es 12/14; se podría bajar a 5 y abaratar el prompt |
| Troceado | 450 tokens ≈ 337 palabras; el prompt recorta a 320 | las últimas ~17 palabras de los trozos largos no llegan al LLM |
| Tipos indexados | md, txt, eml, html, pdf | **pptx y Excel fuera** |
| Umbrales Jev | 0,80 publicar · 0,30 descartar | fijados con un banco de 12 casos; poco para calibrar |
| Embeddings | EmbeddingGemma 2 a 256 d | en lugar de `multilingual-e5-small`: añade imagen y 8K de contexto; se decide con la tabla de arriba |
| RRF `K` | 60 | valor del artículo original (Cormack et al., 2009) |
| Whisper | `small`, int8 | compromiso velocidad/calidad en CPU; `B5T4_STT_MODEL=large-v3-turbo` si sobra tiempo |

## 5. Privacidad
Todo lo que puede correr en local corre en local: transcripción, embeddings, índice y voz. Salen del PC solo
los fragmentos que se mandan al LLM (OpenRouter) y a Jev (TypeSafe). En OpenRouter se recomienda activar
«no usar para entrenamiento» y solo proveedores sin retención de datos.
