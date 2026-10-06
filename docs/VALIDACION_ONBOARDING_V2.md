# Validación de Onboarding v2 · 7 octubre 2026

La entrega parte de `95fe4c5`, conservado en `codex/onboarding-completo`, y se desarrolla en
`codex/onboarding-v2` dentro del worktree aislado. Las salidas y datos internos permanecen fuera de Git.

## Ejecuciones con datos reales

| Medida | Analista junior de Alpha | Responsable de equipo |
|---|---:|---:|
| Máximo solicitado | 120 s | 300 s |
| Duración del MP4 | 112,04 s (93,4 %) | 278,98 s (93,0 %) |
| OpenRouter confirmado | 1,917574 USD | 2,492047 USD |
| Reservas sin confirmar | 0 | 0 |
| Capítulos de referencia | 7 | 8 |
| Palabras explicativas en párrafos | 1.512 | 2.183 |
| Filas de tablas | 32 | 36 |
| Hechos publicados | 76 | 88 |
| Respaldo factual mínimo Jev | 0,81 | 0,82 |
| Documentos leídos, además de contextos | 31 | 24 |
| Escenas / tipos de composición | 7 / 6 | 9 / 6 |
| Palabras de locución | 238 | 659 |
| Peticiones Jev acumuladas | 464 | 777 |
| Comprobaciones reutilizadas | 732 | 4.734 |

Los importes y peticiones incluyen los intentos realizados durante el desarrollo y sus reanudaciones.
Jev se registra por separado; estas cifras no estiman su factura. Las notas editoriales, de audio y de
composición son valoraciones de calidad, independientes del respaldo documental.

Los dos vídeos están en 1920×1080, H.264/AAC, y se han decodificado completos. La ejecución operativa
se centra en mandato Alpha, maestro, corte semanal, controles y herramientas vigentes. La de mayor
responsabilidad amplía carteras modelo, mandatos y jurisdicciones, cadencias y proyectos pendientes.
Ambas mantienen equipo, organización, reglas y documentación como base común.

## Piezas completas en el worktree

Operativo: `out/onboarding/20261007-003029-v2-8727/`.

- [Informe](../out/onboarding/20261007-003029-v2-8727/informe.html)
- [Infografía](../out/onboarding/20261007-003029-v2-8727/infografia.png)
- [Vídeo](../out/onboarding/20261007-003029-v2-8727/video.mp4)

Responsable: `out/onboarding/20261007-003029-v2-4115/`.

- [Informe](../out/onboarding/20261007-003029-v2-4115/informe.html)
- [Infografía](../out/onboarding/20261007-003029-v2-4115/infografia.png)
- [Vídeo](../out/onboarding/20261007-003029-v2-4115/video.mp4)

Cada carpeta conserva briefing, fuentes y pasajes, hechos aceptados y pendientes, capítulos, dirección,
guion, ilustraciones, clips, revisiones, consumo y validaciones. Los enlaces son locales: los artefactos
internos no se distribuyen con el repositorio. Los encargos reproducibles están en `examples/onboarding/`.

## Comprobaciones realizadas

47 pruebas pasan: las 24 anteriores y 23 de v2. Cubren conversación y aislamiento, confirmación,
presupuesto, costes inciertos y reconciliación, fuentes y briefing modificados, compatibilidad,
reparación factual acotada, caché Jev entre procesos, reutilización de voz y bloqueo de una ejecución.
Las pruebas de Chromium comprueban GSAP/D3 locales, logo, seis elementos en una composición focus,
límites de transición y saltos hacia atrás. Las capturas finales no presentan desbordamientos.

La interfaz se ha probado con dos sesiones independientes: conversación real, resumen editable,
petición de fondo azul que conserva la marca, reinicio del encargo y apertura de resultados v1/v2.
Los informes se han comprobado a 1440 y 390 píxeles de ancho, sin desbordamiento horizontal ni imágenes
perdidas. Los logos conservan proporciones y espacio de protección; se utiliza Verdana porque Myriad
Pro no está disponible en este equipo.

La revisión de voz escucha primero sin guion; cuando aparecen diferencias de ortografía de nombres
propios, compara el sonido con el guion y conserva ambos resultados. Jev comprueba después añadidos
y omisiones por frases. La pista de cinco minutos requirió un ajuste residual de tempo de 0,960,
sin recortar locución ni cambiar el tono, antes de la revisión final.

Durante la validación se corrigieron respuestas truncadas por tokens de razonamiento, relaciones
inferidas sin respaldo, resúmenes que perdían condiciones, recortes en nodos del organigrama,
solapamientos de composiciones con cinco elementos y escrituras atómicas bajo Windows. Los errores
preservaron sus artefactos; las reanudaciones reutilizaron comprobaciones y audio compatible.

## Comparación con v1

V1 entregaba 39 hechos, siete escenas y 84,85 segundos. V2 incorpora documentos de referencia con
capítulos explicativos, tablas, pendientes e índice de fuentes; la duración del vídeo no limita el
informe. La infografía utiliza síntesis y relaciones verificadas. Los vídeos añaden ilustraciones,
composiciones variadas y movimientos GSAP, con voz Algieba revisada y duración medida. La marca queda
controlada por los recursos Andbank versionados y el código.

La naturalidad y la utilidad final siguen siendo criterios de revisión humana; las notas del modelo
no los convierten en garantías objetivas. Música, efectos sonoros, avatares y agentes 2/3 quedan fuera.

## Auditoría reproducible

```powershell
uv run pytest
uv run python scripts/validate_onboarding_v2.py "out/onboarding/20261007-003029-v2-8727" "out/onboarding/20261007-003029-v2-4115"
```

El resumen comprobado está en `out/validacion_onboarding_v2.json`; evidencia visual y de interacción
en `out/validacion-v2-interfaz/`. El auditor verifica los hashes de fuentes, el umbral, las referencias,
el presupuesto, las revisiones y la decodificación sin realizar llamadas a proveedores.
