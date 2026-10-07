# Agente 1 · ejecución del onboarding

El flujo lee los 20 contextos completos, planifica ocho bloques y consulta documentación vigente
para redactar un informe con citas. Jev comprueba sus afirmaciones. La infografía y la locución se
derivan de los hechos publicables y también se verifican contra ellos. Kokoro y Chromium/ffmpeg
producen el vídeo localmente. No requiere LangChain ni LangGraph.

## Preparación

Configurar `.env` con `B5T4_DATA_DIR`, `OPENROUTER_API_KEY` y `JEV_API_KEY`. Instalar dependencias y
Chromium según el README y descargar Kokoro. `B5T4_MODELS_DIR` permite reutilizar una carpeta de
modelos existente al trabajar en un worktree; las salidas siempre pertenecen al checkout activo.

```powershell
uv run b5t4 check
uv run b5t4 onboarding
uv run b5t4 ui
```

El onboarding comprueba voz, ffmpeg y Chromium antes de hacer llamadas de redacción. OpenRouter
recibe el catálogo y los fragmentos seleccionados; Jev recibe las afirmaciones y sus pasajes. No
se envía el corpus entero. Las claves se leen de `.env` y no se incluyen en los artefactos.

## Informe y reanudación

```powershell
uv run b5t4 onboarding --report-only
uv run b5t4 onboarding --resume "out/onboarding/<ejecucion>"
```

Sin Jev, `--report-only` produce un borrador identificado como no verificado. Las piezas finales
requieren verificación y al menos dos hechos publicables por bloque. Jev aplica los umbrales de
`config/b5t4.toml`: publicar desde 0,80, revisar entre 0,30 y 0,80, descartar por debajo de 0,30.
Un resultado automático mide respaldo documental; no sustituye la revisión editorial del equipo.

Cada ejecución usa una carpeta distinta, conserva sus etapas JSON y registra errores en
`ejecucion.json`. La reanudación compara hashes SHA-256 de contextos, documentos leídos y manifiesto,
además de modelos y umbrales. Si cambian, requiere una ejecución nueva. Los audios de escenas que
conservan texto, voz y velocidad se reutilizan. El montaje visual se vuelve a producir para recoger
correcciones de plantilla.

## Etapas y código

1. `material.py`: conserva apartados completos, metadatos, anexos, fuentes y huellas del corpus.
2. `plan_outline()`: cubre banco/equipo, personas, secciones, carteras, proceso, calendario, reglas y recursos.
3. `Material.for_block()`: selecciona apartados y resuelve documentos vigentes mediante el manifiesto.
   Admite ruta actual, ruta original, referencia relativa y nombre único. Registra ambigüedades,
   ausencias y tipos no soportados; no ejecuta instrucciones de los documentos.
4. `draft_block()`: redacta hechos con ids de evidencia. Se permite una ronda adicional de consulta
   a documentos del catálogo si quedan lagunas.
5. `verify_block()`: verifica cada hecho, intenta una corrección de los dudosos y excluye lo que
   continúa sin respaldo. Las probabilidades y pasajes se conservan en la caché de comprobaciones.
6. `build_infographic()` y `build_storyboard()`: reciben solo el informe publicado. Se verifican
   tarjetas, relaciones de jerarquía/secuencia y locución contra los hechos citados.
7. `video.narrate()`: mide los audios reales con pausas. Si exceden 120 s, el flujo solicita una
   locución más breve y repite, hasta un máximo de tres intentos.
8. `video.render()`: valida el área legible, dibuja las escenas y monta H.264/AAC. `inspect_video()`
   decodifica el MP4 y comprueba imagen, audio, dimensiones y duración.

`pipeline.py` coordina estas etapas. `schemas.py` define sus contratos. Los renderizadores comunes
conservan sus interfaces; `scene.html` añade `orgchart`, `people`, `flow` y `timeline`, además del
diseño de tarjetas de onboarding. La infografía usa HTML/CSS local y no necesita CDN.

## Artefactos por ejecución

| Archivo | Contenido |
|---|---|
| `ejecucion.json` | Estado, etapa, modelos, hashes de entrada y resultado final |
| `dosier.md`, `fuentes.json` | Evidencias, referencias, documentos consultados y problemas de lectura |
| `indice.json` | Plan de ocho bloques |
| `borrador_*.json`, `ampliacion_*.json`, `ampliado_*.json` | Redacción y ampliaciones intermedias |
| `verificado_*.json`, `verificacion.json`, `comprobaciones.json` | Hechos, decisiones y respaldo documental |
| `informe.md`, `informe.html` | Informe legible con citas y pendientes |
| `infografia.json`, `infografia.html`, `infografia.png` | Estructura y presentación gráfica |
| `guion.json`, `storyboard.json` | Locución, tarjetas y referencias al informe |
| `audio/`, `voz.wav`, `timeline.json` | Audios por escena, pista completa y tiempos reales |
| `escenas.html`, `escena_*.png` | Presentación reproducible y capturas de escenas |
| `video.mp4`, `validacion_video.json` | Vídeo final y comprobación de decodificación |

La interfaz muestra progreso, resultados parciales ante errores, informe, infografía, vídeo y
descargas. El campo de carpeta acepta la ruta indicada por una ejecución. «Abrir resultados
existentes» carga sus artefactos sin llamadas a modelos; «Generar / reanudar onboarding» continúa
las etapas y vuelve a montar el vídeo.

## Límites y validación

Los formatos admitidos son Markdown, texto, CSV, JSON, HTML, correo EML, PDF con texto y PowerPoint.
Los Excel con fórmulas Bloomberg requieren una lectura específica y no se utilizan. Un PDF sin
texto se registra para revisión visual; no se inventa su contenido. Los documentos no vigentes o
las referencias ambiguas quedan excluidos. Las lagunas del informe se muestran como pendientes.

```powershell
uv run pytest -q
```

Las pruebas de onboarding usan datos ficticios, no APIs. Comprueban rutas originales y ambiguas,
límites del corpus, conservación de apartados y anexos, citas, exclusión de hechos sin respaldo,
cambios de fuentes al reanudar, tiempos reales de voz, reutilización de clips y errores de interfaz.
La ejecución integrada y la revisión visual de esta entrega están documentadas en
[VALIDACION_ONBOARDING.md](VALIDACION_ONBOARDING.md).
