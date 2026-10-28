# Verificación real de visuals

Objetivo: comprobar con Cloudflare lo que las pruebas no pueden: imágenes de un video completo, consistencia de personajes con referencia y la cuota. Unos 30 minutos y entre 20 y 60 imágenes (≈ 100 neuronas cada una; tienes 10 000 al día).

## Antes de empezar
1. `docker compose build`, y en `.env`: `CLOUDFLARE_ACCOUNT_ID` y `CLOUDFLARE_API_TOKEN`.
2. Un video largo con guion aprobado y voz hecha (o en manual): crea `evergreen new "Aventura en el estanque" --format long --language es`, genera el guion y apruébalo. Los guiones nuevos traen varias tomas por escena; uno antiguo, solo una.
3. Anota en el panel de Cloudflare las neuronas de hoy.

## A. Hojas de personajes (long)
`evergreen run <id>` hasta `characters`: revisa `stages\characters\personaje-*.jpg`. ¿Se parecen a la descripción? Si no, edita `cast.yaml` y borra esa imagen para repetirla. Aprueba con `evergreen approve <id> characters`.

## B. Escenas
`evergreen run <id>`: tarda unos 10 s por imagen. Revisa `stages\scenes\`:
- ¿El personaje se parece a su hoja en todas las imágenes?
- ¿Aparece en la **pose** que pide la toma, o copia la pose de la hoja? (la referencia tiende a copiarla)
- ¿El estilo (colores, fondos) es coherente entre escenas?
- ¿Hay texto o letras en las imágenes?

## C. Rima (9:16)
`evergreen new "Los patitos" --format rhyme` y ejecútalo hasta `visuals`. Mismas preguntas.

## D. Manual y clips
Con `EVERGREEN_IMAGE_MODE=manual`, ejecuta una etapa y abre `MANUAL.md`: ¿el prompt es claro?, ¿el paso de Flow se entiende? Anima una imagen en Flow (9:16 si es rima) y guarda el clip como `<clave>.mp4` en `inbox/`.

## Qué reportar
1. Neuronas gastadas (antes y después) y si el contador de cuota diaria subió.
2. Consistencia del personaje (bien/regular/mal), pose y estilo, con 2 o 3 imágenes de ejemplo.
3. Si hubo cuota agotada o errores: el texto exacto.
4. Flow: si acepta la imagen y la proporción 9:16.
