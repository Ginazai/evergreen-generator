# Verificación real de script-writer (con tu clave de Gemini)

Objetivo: comprobar con la API real lo que las pruebas no pueden: que Gemini acepta el esquema, que los guiones validan y que la cuota alcanza. Dura unos 15 minutos.

## Antes de empezar
1. En Google AI Studio crea una clave y copia `.env.example` a `.env`; pega la clave en `GEMINI_API_KEY=`.
2. En AI Studio anota los **límites diarios** (solicitudes por día) de `gemini-3.8-flash` y de `gemini-3.5-flash-lite`.
3. `iniciar.bat` (abre una terminal con los comandos de `evergreen`).

## Las 4 combinaciones
Para cada línea: ejecuta `evergreen run <id>` con el id que imprime `new`, abre `stages\script\script.md`, y anota el resultado.

```
evergreen new "Los patitos"      --format rhyme --language es --brief "patitos que aprenden a nadar"
evergreen new "The little ducks" --format rhyme --language en --brief "ducklings learning to swim"
evergreen new "Aventura en el estanque" --format long --language es --brief "una amiga descubre un eco misterioso"
evergreen new "Pond adventure"   --format long --language en --brief "a friend discovers a mysterious echo"
```

## Qué anotar por cada una
- ¿La etapa terminó (`evergreen status <id>` muestra `script: esperando aprobación`)? Si falló, copia el mensaje completo y, si existe, el contenido de `stages\script\raw.txt`.
- ¿Las rimas riman en ese idioma? ¿Los personajes tienen sentido? ¿Se nota la variación (estructura, tono, giro)?
- Si es la segunda de un mismo formato: ¿se parece a la primera?

## Qué reportar al final
1. Las 4 combinaciones: ¿validaron? (sí/no y mensaje de error).
2. Cuántas solicitudes consumiste (AI Studio, pestaña de uso) y si apareció algún límite.
3. Calidad de las rimas: bien / aceptable / mala, con un ejemplo si es mala.
4. Los límites diarios de los dos modelos anotados antes.

Con eso decidimos el modelo por defecto y afinamos el prompt o el umbral de similitud si hace falta.
