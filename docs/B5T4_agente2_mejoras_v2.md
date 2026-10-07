# Agente 2 (Opinión Corporativa) · Mejoras de la versión definitiva — 7-oct-2026

Alcance: cambios pequeños, sin tocar la arquitectura (los seis pasos del pipeline siguen siendo los mismos),
orientados a cuatro ejes: coste, latencia, exactitud y calidad del contenido para el cliente. Ficheros tocados:
`agents/opinion/{extract,compare,explain,rationale,llmcall,pipeline,report,video}.py`, nuevo `agents/opinion/tts.py`,
`templates/informe.html`, `config/b5t4.toml`, `tests/test_opinion.py`, `README.md` y una línea en `render/video.py`
(`B5T4_CHROMIUM`, para usar un Chromium ya instalado). No se ha tocado nada de los agentes 1 y 3.

Validación: 15 tests pasan; ejecución completa en modo referencia (sin LLM) y con la caché real de las dos
ediciones leídas en el PC; vídeo completo renderizado de principio a fin (82 s, h264 + aac) con la voz de respaldo.
Lo que depende de la clave de OpenRouter (frases, porqués, voz de Gemini) se valida en la primera ejecución en el
PC: `uv run b5t4 opinion --video`.

## 1. Exactitud

| # | Qué fallaba | Qué se ha hecho | Impacto medido / esperado |
|---|---|---|---|
| 1 | **La caché guardaba las comprobaciones, no solo la lectura.** Al ampliar la tolerancia de divisas, las ediciones ya leídas seguían mostrando «⚠ suma de control fallida» en USDCHF, EURCHF y EURGBP: avisos falsos en el informe del cliente. | `extract._recheck`: al cargar de caché se recalculan evidencias literales, sumas de control, conclusiones y textos normalizados. La caché solo conserva lo que cuesta dinero (la lectura del LLM). También corrige la ruta del PDF a la de la máquina actual. | **Medido con la caché real: 4 avisos falsos → 0.** Cualquier mejora futura del código llega a las ediciones ya leídas sin volver a pagar. |
| 2 | Un año se leía como objetivo: «cierre de 2026: 1.600» → `[2026, 1600]`. En la edición 1T-2027 habría saltado un cambio de objetivo falso en cada activo con esa redacción. | `compare._nums` ignora los años (cuatro cifras sin punto de miles; un nivel se escribe «2.050»). Test añadido. | Evita 2-4 falsos cambios por edición a partir del próximo trimestre. |
| 3 | La región de una página se detectaba por subcadena: «ust» coincidía con «ajuste» o «robusto». Una página mal detectada convierte sus activos en `otro:` y aparecen como «desaparece». | `extract.detect_region` con límites de palabra. Test añadido. | Elimina un modo de fallo silencioso (hoy no se daba; con la plantilla de otra región, sí). |
| 4 | Si Jev fallaba, el error se trataba al revés: en las frases tumbaba toda la ejecución (tras pagar el LLM); en los porqués, el argumento se publicaba como verificado. | Reintento único en ambos; si persiste, estado «sin verificar» (se enseña sin marca de verificada). Se registra en el log cuántas llamadas fallaron. | Ninguna frase se publica como verificada sin serlo; un corte de red ya no cuesta una ejecución. |
| 5 | Frases del modelo con respaldo 0,30-0,80 se publicaban con su redacción original marcadas «a revisar». Ejemplo real: «La Reserva Federal ha revisado al alza la senda…» (0,50) cuando la cita hablaba de la senda que descuenta el mercado. | Tras la reescritura, lo que sigue por debajo de 0,60 se sustituye por la frase factual (`explain.KEEP_MIN`). Entre 0,60 y 0,80 se mantiene marcada. | El cliente no lee ninguna atribución floja; el porqué lo aportan los argumentos con cita literal. |
| 6 | El reintento de la tabla sinóptica reenviaba la misma imagen con el mismo prompt a temperatura 0: misma respuesta, doble coste de visión. | Segundo intento con tres bandas en vez de dos (recortes distintos). Se deja de pedir el «color» del objetivo, que era ruido no usado. | Cuando se dispara, un reintento útil en vez de uno inútil; −300 tokens de salida por lectura. |
| 7 | Textos literales con el espaciado del PDF en columnas: «dif . obj.: 500 bps ;», «NEUTRAL - SOBREPONDERAR», evidencias que empezaban a media palabra. | Normalización en `_clean_views` y ventana de evidencia alineada a palabra. | Píldoras y citas limpias; el mismo activo se escribe igual en titular, tarjeta y tabla. |

## 2. Calidad del contenido (cliente externo)

| # | Antes | Ahora |
|---|---|---|
| 8 | **Porqué sin contexto**: el modelo veía solo la página nueva y la misma página se enviaba hasta tres veces (core y periferia europea, México local y USD). Argumentos duplicados y sin saber qué era nuevo. | `rationale` envía **un bloque por página** con todos los cambios que se justifican en ella y, como contexto, **el párrafo equivalente de la edición anterior**. Cada argumento (2-4 por cambio, 12-24 palabras) lleva su cita literal de la edición nueva, se comprueba en el texto y se marca **«nuevo en esta edición»** cuando no estaba en la anterior: eso es el cambio de discurso de la casa, no solo de cifra. Las citas repetidas entre cambios de la misma página se eliminan. El informe enseña además la cita **en su contexto** (±220 caracteres). KPI nuevo: argumentos con cita, y cuántos son nuevos. |
| 9 | KPI «22/28 frases verificadas» contaba 6 frases factuales que nunca pasan por Jev como si fueran fallos. | «22/22 verificadas por Jev · 6 factuales». |
| 10 | Petróleo: «Banda objetivo: 80-90 USD/barril (Comprar por debajo de 80 USD; vender por encima de 90 USD) (80-90 USD/barril)». Regla operativa literal en un documento que vigila el tono MiFID, y la banda dos veces. | «80-90 USD/barril». La regla «comprar/vender» del PDF no se reproduce; para un activo con solo objetivo, el objetivo una vez. Test añadido. |
| 11 | Sujeto rotatorio «Andbank / la casa / la entidad / la firma» (lo pedía el prompt): prosa de máquina, peor en voz. | «Andbank», y «la casa» como mucho una de cada cuatro frases. |
| 12 | Enlaces «abrir el PDF» a `file:///C:/Users/javie/…`: muertos para cualquier destinatario. | `[opinion] pdf_url_base`: si los PDF están publicados (intranet/SharePoint) los enlaces apuntan ahí; vacío = fichero local (útil para el equipo). La página citada y la cita literal se ven siempre. |
| 13 | HTML de 1,8 MB (la imagen de la tabla, 886 kB en PNG). | Tabla en JPEG a 1.200 px: ≈ 300 kB; informe ≈ 1,2 MB. |
| 14 | **Vídeo**: 136 s (tope 120); argumentos cortados «…presión sobre la inf…»; tarjetas de tendencias vacías; «salen 2 temas» con una sola tarjeta; «eleva 18 rendimientos» contando diferenciales de crédito; escena de Shenzhen vacía 7 s; «MEDIO-ALTO», «4T 2026» y «rend. obj.» leídos tal cual. | Presupuesto con 2,8 palabras/s (medido; `video.words_per_second`, antes un valor fijo sin usar): si se pasa, primero menos razones y luego sin la escena del oro, nunca sin un cambio de recomendación. Nada se trunca: se elige el argumento que cabe, los nuevos primero. Tarjetas con el resumen de cada tema; hasta tres en pantalla y los nombres de los que salen en voz. Solo rendimientos en el recuento («18 de sus 19 rendimientos objetivo»). Shenzhen: «La casa no detalla el motivo en esta edición», en voz y en pantalla. Voz: «medio alto», «cuarto trimestre de 2026», «rendimiento objetivo». Medido: 207 palabras → 82 s. |

## 3. Latencia

| # | Cambio | Impacto |
|---|---|---|
| 15 | Las frases (`explain`) y los porqués (`add_rationale`) eran independientes y se ejecutaban en serie: 36,6 s el paso 4. Ahora en paralelo (dos hilos). | Esperado: paso 4 de 36 s a **18-22 s** y la ejecución completa de 37 s a **≈ 20 s** (confianza media; se mide en el PC). |
| 16 | Jev: reintento en vez de esperar 30 s a una llamada caída y abortar. | Sin cuelgues por una llamada lenta. |
| 17 | Voz de Gemini: las escenas se sintetizan en paralelo (4 hilos) y cada frase se guarda en `index/opinion/voz/`. | Voz del vídeo en ≈ 5-10 s (Kokoro en local: 32 s medidos). Una frase repetida entre ejecuciones no se vuelve a sintetizar ni a pagar. |

El render de fotogramas (≈ 140 s para 82 s de vídeo, CPU) no se ha tocado: es el motor compartido.

## 4. Coste

| Partida | Antes | Ahora |
|---|---|---|
| Informe (ediciones ya leídas) | 0,038 $ | **≈ 0,033 $**: el porqué envía cada página una vez (−7 k tokens de entrada, −25 % del paso). Los tokens de razonamiento ahora se ven en el log y en `cambios.json` (antes se pagaban sin saberlo). |
| Lectura de una edición nueva (una vez por trimestre) | ≈ 0,010 $ | Igual, −300 tokens (sin el color de la tabla). |
| Vídeo | 0 $ (Kokoro) | **≈ 0,03 $** con Gemini 3.8 Flash TTS (9 $/M tokens de audio, ≈ 32 tokens/s; Google anuncia el doble desde el 1-ene-2027: 0,06 $). Variante `flash-lite-tts` a 6 $/M si se quiere ahorrar. |
| **Total informe + vídeo** | 0,038 $ | **≈ 0,065 $** |

## 5. Voz de Gemini: cómo funciona y qué comprobar

`agents/opinion/tts.py`, configurado en `[opinion.tts]`: `provider = "gemini"`, modelo `google/gemini-3.8-flash-tts`
por OpenRouter (misma clave), voz `Charon`, instrucción de estilo en lenguaje natural. Si falla por lo que sea
(sin clave, error de red, audio no decodificable), **todo** el vídeo se hace con Kokoro: nunca se mezclan voces. El
proveedor usado queda en `video/estadisticas.json` junto al coste y los tiempos.

Es la única pieza no probada de extremo a extremo (en el entorno de desarrollo no hay clave). Dos cosas a
comprobar de oído en la primera ejecución: que la voz y el estilo se aplican (OpenRouter no documenta cómo pasa
`speech_config` a Gemini) y cómo lee «5,00 %» y «+75 pb». Si el estilo no se aplica, el plan B es la API de Google
directa con `google-genai` (clave propia, con nivel gratuito).

## 6. Pendiente (fuera de «cambios sencillos»)

- Dos audiencias (`--audiencia cliente|interna`): la de cliente sin insignias, porcentajes de respaldo ni coste.
- Emparejar tendencias por embeddings en vez de por título (hoy acierta, pero por Jaccard).
- Si una edición futura exporta la tabla sinóptica como texto, leerla sin visión.
- Datos anonimizados en `data/sample/` para la demo (afecta a los tres agentes).
