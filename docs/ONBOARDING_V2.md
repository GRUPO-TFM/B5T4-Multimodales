# Onboarding v2

La conversación recoge puesto, experiencia, objetivo, área y duración. El usuario revisa los campos y
confirma una vez. A partir de ahí el sistema investiga, verifica, redacta y produce las tres piezas,
con revisiones automáticas y etapas reanudables. Un nuevo encargo crea una ejecución independiente.

V1 permanece en `codex/onboarding-completo` (`95fe4c5`); esta entrega vive en `codex/onboarding-v2`.
Los encargos de ejemplo están en `examples/onboarding/operativo.json` y `responsable.json`.

## Interfaz

```powershell
uv run b5t4 ui
```

En la pestaña 1, describir el perfil y qué necesita conocer. El sistema pregunta solamente si faltan
puesto u objetivo; utiliza experiencia de incorporación, área Gestión Discrecional y dos minutos
como valores por defecto. Jev comprueba la interpretación del puesto y objetivo antes de presentarla.
Los campos del resumen pueden editarse. El vídeo admite de uno a cinco minutos y utiliza la duración
elegida como máximo, buscando ocupar entre el 90 % y el 100 %.

«Confirmar encargo y generar» inicia la ejecución. «Generar solo el informe» limita la salida al
documento de referencia. Para cambios, usar «Nuevo encargo». El campo de resultados conserva la
apertura y reanudación de ejecuciones v1 y v2. Abrir resultados no llama a los modelos.

## CLI y API

```powershell
uv run b5t4 onboarding --brief "mi-encargo.json"
uv run b5t4 onboarding --brief "mi-encargo.json" --report-only
uv run b5t4 onboarding --resume "out/onboarding/<ejecucion>"
```

```json
{
  "role": "Analista junior de Alpha",
  "experience": "Conocimientos básicos de mercados",
  "objective": "Conocer el proceso semanal, los controles y las responsabilidades",
  "area": "Sección Alpha",
  "duration_seconds": 120,
  "budget_usd": 5
}
```

`agents.onboarding.run(brief=OnboardingBrief(...))` selecciona v2. Sin briefing se conserva v1.
La reanudación identifica automáticamente v2 mediante su `brief.json`.

## Etapas

1. Recoger y confirmar el encargo; registrar conversación y consumo.
2. Planificar capítulos comunes y específicos, contextos y documentos vigentes.
3. Extraer hechos atómicos, verificar con Jev y conservar lagunas; ampliar fuentes cuando sea útil.
4. Redactar capítulos de referencia con párrafos, tablas y citas legibles.
5. Revisar claridad, relevancia y coherencia mediante una llamada independiente; volver a verificar lo corregido.
6. Dirigir la narrativa, diagramas e ilustraciones conceptuales bajo la identidad Andbank.
7. Escribir y verificar storyboard, locuciones, etiquetas, jerarquías y secuencias.
8. Sintetizar voz, medir duración real y ajustar la locución.
9. Revisar audio y capturas; comprobar cortes, correspondencia semántica y reproducción determinista.
10. Montar y decodificar el MP4 completo; guardar estado y evidencia.

Cada etapa limita la corrección a dos rondas. Los errores preservan resultados parciales. El informe
de referencia no tiene la limitación de duración del vídeo; infografía y vídeo seleccionan sus ideas
principales. Solo hechos con respaldo de al menos 0,80 pueden alimentar las piezas publicadas.
Las locuciones se verifican por frases y se reparan únicamente las afectadas. Una relación que no
supera el umbral se registra en `ajustes_relaciones.json` y pasa a un mapa sin conectores; sus textos
siguen necesitando respaldo. El tamaño y la disposición de los componentes se adaptan al número de elementos.
Las ilustraciones se generan después del storyboard, únicamente para los componentes que las muestran;
la portada del informe reutiliza uno de esos recursos.

## Marca y motor

La skill y los masters están versionados en `src/b5t4/render/brand/andbank/`. Las tres piezas usan
blanco, negro, rojo `#D52B1E` y gris cálido `#928B81`, Myriad Pro o Verdana y el logo a la derecha.
La identidad es fija: las peticiones de cambio de paleta no se trasladan a los renderizadores.

GSAP 3.15.0 controla los movimientos y transiciones; D3 7.9.0 calcula diagramas SVG. Las bibliotecas,
sus versiones y referencias de licencia están en `render/vendor/`. El HTML contiene sus recursos
locales incrustados y puede abrirse sin CDN. El render conserva Chromium/ffmpeg y la interfaz
`render(t)`; verifica saltos hacia atrás y adelante, además de límites y desbordamientos.
El logo conserva el master y sus proporciones; CSS elimina su margen blanco sobrante y mantiene
el espacio de protección. En el formato móvil se oculta el tagline y se trunca el símbolo según la skill.
Lottie se reserva para una futura biblioteca de animaciones corporativas aprobadas.

## Modelos y presupuesto

La configuración `[onboarding_v2]` define imagen, voz y presupuesto. El modelo principal y el de
revisión multimodal mantienen la configuración `[llm]`:

- Gemini 3.8 Flash: conversación, contenido, dirección, revisión visual y del audio.
- Gemini 3.1 Flash Image: ilustraciones conceptuales; datos, letras, gráficos y logos se dibujan por código.
- Gemini 3.8 Flash TTS: voz Algieba, con dirección de entrega en `speech_metadata` separada del texto.
  El proveedor exige PCM; se conserva a 24 kHz mono y se guarda en WAV.
- Jev: interpretación y respaldo semántico/documental; su consumo se registra por separado.

OpenRouter reserva una estimación conservadora antes de cada llamada y reconcilia costes mediante
su identificador de generación. Las reservas pendientes siguen contando, incluso después de un
error de red. Antes de detenerse por falta de presupuesto se intenta recuperar su coste definitivo.
La interfaz distingue el importe contabilizado de las reservas aún sin confirmar. La factura del
proveedor es la fuente de verdad; las estimaciones no garantizan por sí mismas un límite bancario.
El sistema no aumenta el presupuesto ni cambia de voz automáticamente.
Tras medir la voz se corrige el guion hasta dos veces. Una desviación residual permite un ajuste
de tempo de hasta el 8 % con ffmpeg, sin cortar palabras ni cambiar el tono; se registra en la línea
temporal y el audio resultante vuelve a revisarse. Una desviación mayor detiene la entrega.
La escucha inicial no recibe el guion. Si su transcripción difiere en nombres o cifras, una segunda
escucha compara explícitamente sonido y guion; conserva ambas revisiones y vuelve a exigir 0,80 a Jev.

## Artefactos y reanudación

Además de las piezas finales, se guardan `brief.json`, conversación, índice, investigaciones,
`verificacion.json`, capítulos editoriales, `direccion.json`, `guion.json`, ilustraciones, audios,
revisiones, validación de diseño, costes y `ejecucion.json`. Los datos y artefactos quedan fuera de Git.
`solicitudes/` guarda los prompts y respuestas nuevos, con hashes de los medios en lugar de duplicar
su base64. Los costes conservan el identificador y hash de cada petición. Las valoraciones editoriales
y visuales son notas de calidad de 1 a 5; no representan probabilidades de veracidad.

La reanudación rechaza cambios en briefing, fuentes, manifiesto, modelos o marca. Los hashes de
código/prompts y dependencias por etapa invalidan contratos que deban reconstruirse. La caché de
respuestas incorpora prompt y esquema; los clips incorporan modelo, voz, texto y dirección vocal.
Las comprobaciones de Jev se comparten mediante SQLite con escrituras seguras entre procesos, y
cada ejecución conserva su propio expediente de evidencias y consumo.
Los contratos válidos pueden reutilizarse después de una corrección del código, conservando su
procedencia y revalidando referencias. Un contrato que ya no encaja se reconstruye. La pista de voz
solo se reutiliza si coinciden texto, modelo, voz, clips y hash del WAV. Cada carpeta tiene un bloqueo
del sistema operativo para impedir dos reanudaciones simultáneas; se libera si termina el proceso.

## Código y validación

| Responsabilidad | Módulo |
|---|---|
| Conversación y confirmación | `agents/onboarding/conversation.py` |
| Contratos | `agents/onboarding/v2_schemas.py` |
| Etapas, caché y reanudación | `agents/onboarding/v2_pipeline.py` |
| Investigación, Jev, referencia y guion | `agents/onboarding/v2_content.py` |
| Voz, revisión auditiva y capturas | `agents/onboarding/v2_media.py` |
| OpenRouter, modalidades y presupuesto | `models/openrouter.py` |
| Marca y piezas escritas | `render/brand.py`, `render/onboarding.py` |
| Escenas y animación | `render/templates/*v2*`, `scene.html`, `render/video.py` |
| Frontal y CLI | `app/ui_onboarding.py`, `app/ui.py` (montaje), `cli.py` |

```powershell
uv run pytest
uv run python scripts/validate_onboarding_v2.py "out/onboarding/<operativo>" "out/onboarding/<responsable>"
```

El auditor no llama a proveedores: comprueba firmas y fuentes, referencias publicadas, presupuesto,
duración, revisiones y decodificación completa. Su resumen se guarda fuera de Git en
`out/validacion_onboarding_v2.json`. Evidencia integrada: `docs/VALIDACION_ONBOARDING_V2.md`.
