# Onboarding v2 · Eficiencia (8-oct-2026)

Diagnóstico y cuatro cambios acotados para reducir la latencia y el coste del agente 1 sin tocar sus contratos,
sus umbrales de verificación ni la calidad de lo que publica. Los cuatro cambian **cuándo** y **cuántas veces**
se hace el trabajo, no **qué** se comprueba.

## Punto de partida (validación de Diego, 7-oct)

| Medida (vídeo de 120 s) | Valor |
|---|---:|
| OpenRouter | 1,92 $ |
| Peticiones a Jev | 464 |
| Duración de la ejecución | ≈ 10 min |

Lectura del código: siete capítulos independientes se investigaban y redactaban **en serie**; cada párrafo o fila
sin respaldo obligaba a **regenerar el capítulo entero** y a volver a pagar las verificaciones de los párrafos ya
aptos; cada afirmación viajaba a Jev en **una petición HTTP propia**; y los ~2.800 fotogramas del vídeo se
capturaban con **un solo navegador**. Nada de esto depende del volumen de datos: es orden de ejecución.

## Cambios

### A · Capítulos en paralelo (`v2_pipeline.py`)
`research_chapter()` encapsula lo que antes era el cuerpo del bucle (investigación → ampliación si hay lagunas →
verificación) y `parallel()` lo aplica a los capítulos con `onboarding_v2.workers` hilos (6 por defecto, 1 = en
serie como antes). La redacción del documento de referencia (`write_chapter`) va igual. Lo compartido entre hilos
ya tenía cerrojo (libro de consumo de OpenRouter, caché de Jev) o lo tiene ahora: `StageArtifacts` (metadatos de
etapas) y `PersonalizedMaterial` (lecturas de documentos). Los resultados conservan el orden del plan; un error en
un capítulo se propaga igual que antes.

### B · Fotogramas en varios navegadores (`render/video.py`)
`render(t)` dibuja cada instante desde cero (Diego lo prueba con saltos hacia atrás), así que el tramo de
fotogramas se reparte entre `video.render_workers` navegadores (4 por defecto). Mismo HTML, misma escala, mismo
JPEG; comprobación de que no falta ningún fotograma antes de llamar a ffmpeg; `preset veryfast` con el mismo
`crf 20`. Esto beneficia también al vídeo del agente 2. Medido en el contenedor de desarrollo (2 núcleos): 140 s →
94 s para 2.100 fotogramas; en un PC de 8-16 hilos la ganancia esperada es ~4×.

### C · Reparar el párrafo, no el capítulo (`v2_content.py`)
`repair_paragraphs()` reescribe sobre sus propios hechos el párrafo que no alcanza el umbral (hasta dos rondas,
mismo patrón que `repair_narrations`) antes de que el contrato del capítulo falle. Solo si tras dos rondas sigue
flojo, el contrato falla y el capítulo se regenera como antes. Los párrafos aptos no se tocan ni se vuelven a
verificar (caché). Queda constancia en `ajustes_parrafos.json`.

### D · Jev por lotes y estadísticas perezosas (`v2_content.py`) — lotes desactivados tras la prueba real, ver abajo
`Checks.many()` agrupa las afirmaciones pendientes por pasaje y envía hasta 5 por petición (`_ask` admite varias
preguntas sobre un estado), en paralelo entre grupos. La caché sigue siendo **por afirmación**: lo que un lote
comprueba lo reutilizan después `check()` y otras ejecuciones, y viceversa. Las estadísticas (`consumo_jev.json`)
se escriben al cerrar cada lote y en cada etapa, no en cada acierto de caché (antes, cientos de escrituras por
ejecución). Las frases de una locución, las filas de una tabla y los hechos de un capítulo comparten pasaje, así
que el número de peticiones debería bajar de ~460 a ~150.

## Primera ejecución real (8-oct-2026, perfil operativo, 120 s)

Se detuvo en la etapa 7 por un fallo **previo** a estos cambios, que la ejecución destapó: el separador de frases de
la locución partía «… en 10. Seccion Alpha, y … bajo la ruta 99. Old …» en tres trozos, y el del medio («Seccion
Alpha, y toda versión anterior … ruta 99.») no tiene respaldo por sí solo (0,52-0,64). La reparación reescribía la
frase correctamente, conservando los nombres de carpeta, y el separador volvía a partirla. Corregido con
`split_sentences()` (no parte tras una cifra), compartido por la verificación de la locución y la auditoría de
audio. Prueba de regresión añadida.

Hasta ese punto (etapas 1-7):

| Medida | Valor |
|---|---:|
| Tiempo | 7 min 20 s (plan 54 s · investigación 3 min 31 s · referencia 35 s · dirección e infografía 50 s · guion 1 min 24 s) |
| OpenRouter | 0,56 $ (investigación 0,36 $; ampliación 0,08 $) |
| Peticiones a Jev | 155 (240 aciertos de caché) |
| Hechos publicados / a revisar | 69 / 1 |
| Respaldo mínimo de lo publicado | 0,81 (igual que la validación de Diego) · media 0,94 |

El respaldo mínimo y medio confirma que los lotes de Jev no han movido la calibración. La investigación sigue
siendo el cuello de botella: con 6 capítulos y 4 hilos, dos capítulos esperaban turno (ahora `workers = 6`), y cada
uno encadena borrador + ampliación con peticiones de 120-180 KB. Ese tramo es el que ataca la mejora H (evidencias
por recuperación, pendiente).

## H · Ampliación incremental y catálogo acotado (8-oct-2026, tras la primera ejecución)

Datos de la ejecución real: la investigación costó 0,36 $ de 0,56 $, y dos tercios de su entrada eran las
**ampliaciones**: cuando el primer borrador declaraba lagunas, se elegían documentos nuevos y se pedía un borrador
NUEVO releyendo todo (100-160 mil caracteres por capítulo) para descartar el primero. Además, la elección de
documentos recibía el catálogo entero (253 rutas, 43 mil caracteres) en cada capítulo.

- `expand_research()`: la ampliación lee solo los documentos nuevos y los hechos ya extraídos, y devuelve la lista
  completa (mismo contrato `ResearchDraft`, mismos ids, misma verificación posterior). Entrada de las ampliaciones:
  637 mil → ~310 mil caracteres en esa ejecución.
- `focus_catalog()`: las 150 rutas del catálogo más afines a las lagunas. Comprobado con la ejecución real: las 18
  rutas que eligió el modelo están dentro de las 150 (18/18).
- **Descartado** recortar las evidencias del primer borrador: con un tope de 45 mil caracteres por relevancia
  léxica se perdía el 28 % de los fragmentos que el modelo acabó citando (36/50 conservados). El ahorro no compensa
  el riesgo sobre la calidad del informe.

Ahorro esperado (estimado, no medido): ~0,1 $ y ~20-30 s en el camino crítico de la investigación.

## Ejecución completa con A-D + H (8-oct-2026, perfil operativo, 120 s, desde cero)

| Medida | Validación de Diego (7-oct) | Esta ejecución |
|---|---:|---:|
| Tiempo total | ≈ 10 min (referido) | **5 min 18 s** |
| OpenRouter | 1,92 $ (incluye reintentos de desarrollo) | **0,74 $** |
| Peticiones a Jev | 464 | **177** (+ 365 aciertos de caché) |
| Hechos publicados / respaldo mínimo | 76 / 0,81 | 84 / 0,80 (media 0,92) |
| Vídeo | 112,0 s | 110,8 s, 1920×1080, H.264/AAC, decodificado completo |

Tiempo por etapa: plan 17 s · investigación (7 capítulos) 43 s · referencia y revisión editorial 25 s · dirección e
infografía 51 s · mensajes y guion 37 s · ilustración 15 s · voz 58 s · auditorías de audio y visual 24 s · render
37 s · validación 12 s. Los fotogramas en los cortes entre navegadores son continuos (diferencia media ≤ 0,03).

Cautelas: la caché compartida de Jev venía caliente de la ejecución anterior, y la latencia de OpenRouter varía
mucho entre ejecuciones (el plan tardó 54 s en la primera y 17 s en esta con una petición equivalente), así que no
todo el salto de la investigación (3 min 31 s → 43 s) es atribuible a los cambios. Estimación para una ejecución
en frío: 5-7 minutos.

Calidad: un hecho dice «distribuidores responsables» donde la fuente dice «contribuidores responsables» y Jev lo dio
por respaldado (0,92) dentro de un lote; la misma afirmación sola sacó **0,33**. Los lotes de Jev restan finura, así
que se desactivan (`Checks.BATCH = 1`, una afirmación por petición como en el diseño original; siguen en paralelo y
con caché). Las comprobaciones hechas en lote se borran de la caché compartida (`out/onboarding/cache/`) para que no
se reutilicen. Se pierde parte del ahorro de peticiones de D; el resto de mejoras no depende de esto.

## Lo que no cambia
Umbral de publicación (0,80), descarte (0,30), contratos Pydantic, reanudación por etapas, presupuesto máximo,
auditorías editorial, visual y de audio, y la regla de que todo lo publicado lleva respaldo verificado.

## Pruebas
`tests/test_onboarding_eficiencia.py` (16 pruebas, sin claves): Jev con una afirmación por petición por defecto,
lotes (si se reactivan) con orden y caché por afirmación, caché compartida, reparación de párrafo sin regenerar el
capítulo (y rendición tras dos rondas), `parallel()` con orden y errores, contratos concurrentes en `StageArtifacts`,
cerrojo del material, separador de frases con cifras, `expand_research()`, `focus_catalog()`, receta de la etapa
`ampliado_`, y fotogramas idénticos (±8 niveles de rasterizado) con 1 y 3 navegadores. La suite completa (115
pruebas) se ha pasado tres veces seguidas.

## Cómo medir en el PC
```powershell
Measure-Command { uv run b5t4 onboarding --brief examples\onboarding\operativo.json | Tee-Object onboarding.log }
```
Comparar con la ejecución anterior: `consumo_openrouter.json` (coste), `consumo_jev.json` (peticiones) y el log
(tiempo por etapa). Para volver al comportamiento anterior sin tocar código: `workers = 1` y `render_workers = 1`
en `config/b5t4.toml`.

## Pendiente (no incluido aquí)
Recorte por relevancia de las evidencias del primer borrador (necesita un recuperador mejor que el léxico; el agente
3 tiene uno denso); caché de los capítulos comunes entre perfiles; modelo
barato para los contratos mecánicos; audio a 16 kHz y capturas a 960×540 en las auditorías; tempo de ffmpeg antes
de reescribir la locución.
