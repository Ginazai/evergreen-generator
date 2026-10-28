# Verificación del montaje (en tu PC)

1. `docker compose build` y luego, con un video que ya tenga voz/música/imágenes: `docker compose run --rm app evergreen run <video>`.
2. Abre `stages/assembly/final.mp4`. Comprueba: formato correcto (16:9 long / 9:16 rima), imágenes con movimiento suave, fundidos, música que baja al hablar, sin cortes bruscos al final.
3. Mide cuánto tardó el render (esperado: pocos minutos por video de ~5 min) y anótalo.
4. Sincronía: con voz manual (un solo archivo) el reparto por escena es proporcional al texto y puede desviarse 1–2 s; con voz Gemini/Piper es exacto por escena.
5. Clips de Flow: copia un `.mp4` a `stages/scenes/inbox/escena-1-1.mp4`, borra `stages/assembly` estado con `evergreen run` de nuevo y confirma que esa toma usa el clip (`"clip": true` en `assembly.json`). Si el clip es más corto que la toma, se congela el último cuadro.
6. Si algo falla, el error nombra el archivo y la etapa que falta.
