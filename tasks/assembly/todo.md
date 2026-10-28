# Tareas: assembly

Cada tarea termina con: pruebas en verde, `ruff` limpio, cobertura ≥ 85 %, y revisión tuya. ffmpeg se ejecuta de verdad en las pruebas (se omiten si no está instalado).

- [x] **A1 `timing.py`.** Función pura: guion + duraciones de audio → duración de cada toma (long: reparto por caracteres dentro de cada escena; sin `timeline.json`: reparto sobre todo el texto; rhyme: por líneas y secciones). Criterio: la suma de las tomas es exactamente la duración del audio; escena de una toma, de varias, y guion sin `shots` cubiertos.
- [x] **A2 `inputs.py`.** Localiza y valida audio, música, `images.json`, imágenes y clips (`<clave>.mp4` en inbox, al renderizar). Criterio: cada archivo ausente produce un error que nombra el archivo y la etapa; un clip vacío se ignora.
- [x] **A3 Segmentos.** Un archivo por toma: zoom/paneo alternados sobre la imagen ampliada, o clip recortado al formato (último cuadro mantenido si es corto, corte si es largo). Criterio: `ffprobe` da la duración y la resolución esperadas (1080p, 16:9 o 9:16).
- [x] **A4 Escenas y concatenación.** Fundido cruzado dentro de la escena (un archivo por escena) y fundido a negro entre escenas; concatenación. Criterio: la duración total es la suma menos los solapes esperados, y se mantiene sincronizada con el audio.
- [x] **A5 Audio.** Long: voz + música en bucle con fundidos y ducking, normalizado a −14 LUFS. Rhyme: canción normalizada. Criterio: duración igual a la voz/canción; la música no la alarga.
- [x] **A6 `AssemblyAdapter`.** Orquesta, reanuda por segmento (resumen de entradas en el nombre del archivo), escribe `final.mp4` (temporal + renombrado) y `assembly.json`; `register()`. Criterio: interrumpir y repetir no rehace segmentos; una entrada modificada sí.
- [x] **A7 Docs y verificación real.** README, `docs/verificacion-assembly.md`; render de un video completo en tu PC con medición de tiempo.
