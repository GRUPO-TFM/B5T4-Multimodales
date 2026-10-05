# Plan hasta la entrega (jueves 8-oct-2026, 18:00)

## Reparto (tres personas, una por agente; las capas comunes ya están)

| Persona | Agente | Carpeta | Primer paso hecho | Lo que falta |
|---|---|---|---|---|
| A | 1 · Onboarding | `src/b5t4/agents/onboarding/` | `gather_material()`: dosier de 72.000 caracteres con las secciones 1-5 de los 20 contextos | Índice (LLM) → informe → verificación → infografía → storyboard → vídeo ≤ 2 min; nuevas escenas `orgchart`, `people`, `flow`, `timeline` en `render/templates/scene.html` |
| B | 2 · Opinión Corporativa | `src/b5t4/agents/opinion/` | `list_editions()`: las 4 ediciones ordenadas por fecha | Extracción de recomendaciones (texto + visión) → diff → explicación → informe → vídeo de cambios |
| C | 3 · RAG | `src/b5t4/agents/rag/` | `build_chunks()`: ~2.700 fragmentos con metadatos | Embeddings + BM25 → índice → router → respuesta con citas → Jev → voz; STT de la pregunta; medición con `evals/preguntas_rag.yaml` |
| Todos | Común | `render/infographic.py`, `data/sample/`, README | — | Infografía; copia anonimizada para la demo; capturas y diagrama en el README; vídeo de la demo |

**Repositorio:** `https://github.com/GRUPO-TFM/B5T4-Multimodales` (privado, rama `main`), dentro de la organización del
equipo, como `GRUPO-TFM/B5T2-agentes`.

**Reglas del equipo (heredadas de B5-T1 y B5-T2):** una rama por trabajo y *pull request* a `main`; un notebook, un dueño;
la lógica en `src/`, no en notebooks; ninguna clave en el repo (`.env` está en `.gitignore`); el repo fuera de OneDrive.

**Regla para trabajar en paralelo:** cada persona toca solo su carpeta de `agents/`. Si hace falta cambiar una capa
común (`corpus`, `models`, `render`), se respeta la interfaz documentada en el docstring del módulo.

## Calendario

| Día | Objetivo | Criterio de «hecho» |
|---|---|---|
| Lun 5 | Estructura del repo, configuración, capa de datos, motor de vídeo portado | `uv run b5t4 check` en verde en los tres PC; `uv run pytest` pasa |
| Mar 6 | Primer extremo a extremo de cada agente, aunque sea feo | Agente 1: vídeo de cualquier duración. Agente 2: tabla de cambios correcta frente a `00_EVOLUCION_RECOMENDACIONES.md`. Agente 3: ≥ 10/15 en el golden set |
| Mié 7 | Calidad e integración | Vídeo 1 ≤ 2 min; vídeo 2 con los cambios; RAG con voz; las tres pestañas de Gradio funcionando; copia anonimizada |
| Jue 8 | Congelar antes de las 14:00 | README con capturas, diagramas y costes medidos; demo grabada; entrega a las 18:00 |

## Guion de la demo (3-4 min)

1. El problema: una carpeta de 1.185 ficheros y un empleado nuevo (10 s, captura de la carpeta).
2. Pestaña 1: vídeo de onboarding (≤ 2 min, se enseña un fragmento) + informe + infografía.
3. Pestaña 2: «¿qué ha cambiado en la visión de la casa?» → vídeo de cambios (bono de EE.UU. de infraponderar a sobreponderar).
4. Pestaña 3: dos preguntas por voz («¿a qué correo va la operativa de Luxemburgo?», «¿quién lleva High Yield?») + la pregunta trampa.
5. Arquitectura y costes (una diapositiva del README).
