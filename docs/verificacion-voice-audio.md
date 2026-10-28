# Verificación real de voice-audio

Objetivo: comprobar con la API real y con Piper lo que las pruebas no pueden: la voz de un video largo completo, la reanudación y la calidad en español. Unos 30 minutos. Usa de 4 a 10 de tus 10 peticiones diarias de voz.

## Antes de empezar
1. `docker compose build` (el paquete nuevo trae Piper y el audio).
2. Para tener un guion de un video largo: `evergreen new "Aventura en el estanque" --format long --language es`, `evergreen run <id>`, revisa `stages\script\script.md` y `evergreen approve <id> script`.
3. (Opcional) copia `voices.example.yaml` como `voices.yaml` en tu carpeta de proyectos.

## A. Voz con Gemini
1. `evergreen run <id>` (tarda: espera ~21 s entre peticiones).
2. Revisa `stages\voice\`: un `escena-N.wav` por petición y `timeline.json`.
3. Escucha 2 escenas. Anota: ¿se distinguen las voces?, ¿la pronunciación en español es buena?, ¿el tono sigue la emoción?
4. Anota cuántas peticiones consumió (AI Studio, uso del modelo TTS).
5. Si la etapa falló por cuota, copia el mensaje completo (me dice cómo cambia el texto del error 429 diario) y confirma que al volver a ejecutar retoma sin repetir.

## B. Voz local con Piper
1. En `.env`: `EVERGREEN_VOICE_MODE=piper`.
2. Crea otro video largo (como en "Antes de empezar") y ejecútalo hasta la voz.
3. La primera vez descarga la voz. Si falla con "no existe", pon otro nombre en `PIPER_VOICE` (lista: `docker compose run --rm app python -m piper.download_voices`) y cuéntame cuál usaste.
4. Escucha 2 escenas: ¿aceptable? (todos los personajes suenan igual).

## C. Pasos manuales
`evergreen new "Los patitos" --format rhyme` y ejecútalo hasta `song`: abre `stages\song\MANUAL.md`, comprueba que trae estilo y letra con `[Verse]`/`[Chorus]`, deja un `song.mp3` en `inbox\` y confirma que la etapa avanza.

## Qué reportar
1. A: ¿funcionó el video completo? Peticiones consumidas, calidad de las voces, errores.
2. B: ¿la voz de Piper en español es aceptable? Nombre de la voz usada.
3. C: ¿el MANUAL.md es claro y avanzó la etapa?
4. Si hubo error de cuota: el texto exacto.
