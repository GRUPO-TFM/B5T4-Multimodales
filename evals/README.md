# evals/

- `preguntas_rag.yaml` · golden set del agente 3: pregunta, respuesta esperada y documento fuente. Incluye una
  pregunta trampa cuya respuesta no está en los documentos (el agente debe decir «no consta»).
- Métricas previstas: **acierto** (juez LLM contra la respuesta esperada), **recall@k** de la fuente esperada
  (¿el retrieval trae el documento correcto entre los k primeros?) y **latencia** extremo a extremo.
- Para el agente 2, el golden set es la tabla hecha a mano
  `03. Vision Corporativa y Servicio/01. Opinion Corporativa/00_EVOLUCION_RECOMENDACIONES.md` de la carpeta de datos.

Ficheros `*.local.*` (resultados de ejecuciones) quedan fuera de Git.
