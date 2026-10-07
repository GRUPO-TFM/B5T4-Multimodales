# Validación del onboarding · 6 de octubre de 2026

Entrega aislada en la rama `codex/onboarding-completo`. El checkout original y el corpus de
OneDrive no se han modificado. Los datos internos se han procesado con autorización expresa
mediante OpenRouter y Jev/TypeSafe; los artefactos permanecen en `out/`, excluido de Git.

## Ejecución integrada

Carpeta local: `out/onboarding/20261006-210950-c9b5`.

| Comprobación | Resultado |
|---|---|
| Contextos cargados | 20, conservando apartados completos y anexos |
| Documentos concretos consultados | 17 vigentes; ninguna incidencia de lectura |
| Informe | 8 bloques, 39 afirmaciones publicables con citas |
| Infografía | Organigrama, secciones/personas, proceso y calendario; HTML y PNG |
| Vídeo | 7 escenas, 215 palabras de locución, 84,85 segundos |
| Formato | 1920 × 1080, H.264 y AAC, 3.773.047 bytes |
| Decodificación | MP4 completo decodificado sin errores |
| Interfaz | Carga de artefactos, enlaces de descarga y reproducción comprobadas en Chromium |
| Pruebas automáticas | 24 superadas, sin llamadas externas |

El bloque de calendario se detuvo inicialmente por respaldo insuficiente. Se corrigieron las
afirmaciones compuestas para conservar una sola idea respaldada y se reanudó desde los JSON
guardados. Las piezas visuales también necesitaron correcciones antes de superar la verificación.
Se conservaron los umbrales configurados: solo contenido con respaldo de al menos 0,80 llega a
las piezas finales.

La revisión visual cubrió la infografía y las siete escenas. El render comprueba además que los
textos caben en el área legible. La prueba de interfaz abrió resultados existentes sin repetir
la generación, reprodujo el vídeo y no registró errores de JavaScript. La captura queda en
`interfaz.png`, junto al resto de artefactos.

El informe deja explícitos dos matices documentales: la asignación de administración directa
de Liquidez y la discrepancia entre versiones del maestro Alpha. La verificación comprueba
respaldo frente a las fuentes leídas; no certifica su vigencia organizativa fuera de esa copia.

## Pruebas reproducibles

```powershell
uv run pytest -q
uv run b5t4 onboarding --resume "out/onboarding/20261006-210950-c9b5"
uv run b5t4 ui
```

Las pruebas unitarias usan datos ficticios y no llaman a APIs. Cubren lectura y resolución de
fuentes, citas, exclusión y reparación de afirmaciones, relaciones entre tarjetas, cambios de
fuentes al reanudar, duración medida, caché de voz y carga de resultados parciales y completos.
La reanudación completa requiere las claves y las mismas fuentes que la ejecución original.
Para consultar la entrega basta abrir la carpeta desde la interfaz o abrir sus archivos.

Quedan fuera de esta entrega los agentes 2 y 3, la copia anonimizada y la demo conjunta.
