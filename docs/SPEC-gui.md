# SPEC: gui (Streamlit sobre el núcleo)

Estado: decisiones cerradas (archivar al regenerar; regeneración de elementos sueltos: sí; claves API editables desde la GUI).

## Objetivo
Manejar todo el flujo (crear video, ejecutar, aprobar, completar pasos manuales, editar y regenerar) desde el navegador, sin tocar YAML/JSON. La GUI **no tiene lógica propia**: llama a funciones del núcleo (`project`, `runner`, modelos del guion, `load_cast/voices/style`). Se abre en http://localhost:8501 vía Docker (`docker compose up gui`), solo local, sin login.

## Pantallas
1. **Videos**: lista (título, formato, idioma, estado) + formulario "Nuevo video" (título, formato, idioma, aspecto, brief ≤500).
2. **Video**: una fila por etapa con estado (pendiente / en curso / esperando manual / esperando aprobación / lista / falló / **desactualizada**), y según estado:
   - *Ejecutar* (corre `evergreen run` en un subproceso con registro en vivo; un solo proceso por video, con archivo de bloqueo).
   - *Aprobar* / *Reabrir*.
   - *Esperando manual*: muestra `MANUAL.md`, permite subir los archivos a `inbox/` y continuar.
   - *Vista previa*: guion renderizado, reproductor de audio, galería de imágenes (con ★ de prioridad), reproductor del `final.mp4`, error completo si falló.
3. **Editar** (todas validan con los modelos existentes y guardan de forma atómica; un error se muestra en el campo, no se guarda):
   - Brief y título del video.
   - Guion: título, personajes, escenas (diálogos, emoción, tomas, movimiento), secciones/letra de rima. Editor por formulario; JSON crudo en un desplegable para casos raros.
   - `cast.yaml`, `voices.yaml`, `style.yaml` (por carpeta de proyectos, compartidos entre videos).
4. **Ajustes**: claves (Gemini, Cloudflare; enmascaradas, editables), modos de voz/imagen activos, carpeta de proyectos, ffmpeg disponible.

## Cambio requerido en el núcleo: reabrir etapas
- `runner.reopen(video_dir, stage)`: la etapa vuelve a `pending`; las etapas posteriores que estaban `done` quedan marcadas `stale` (campo nuevo `StageState.stale: bool = False`, aditivo, los manifests viejos siguen cargando).
- Editar algo aguas arriba (cast, estilo, guion, brief) marca como `stale` lo que depende de ello (mapa fijo: guion → todo; voices → voice; style/cast → characters, scenes/visuals) y la GUI lo avisa con un banner: "Cambiaste el guion: voz, escenas y montaje están desactualizados".
- `stale` no se regenera solo: el usuario elige *Regenerar* (gasta cuota) o *Mantener*.
- Al regenerar, los archivos anteriores de la etapa se mueven a `stages/<etapa>/archive/<fecha>/` (no se borran, y los adaptadores no los reutilizan como si fueran nuevos).
- La CLI recibe `evergreen reopen <id> <etapa>` (la GUI y la CLI comparten la función).

## Regenerar un solo elemento (propuesto)
Para una imagen concreta (p. ej. `escena-2-1`) o una escena de voz: botón *Regenerar esta*, que archiva solo ese archivo y vuelve a ejecutar la etapa (los adaptadores ya son reanudables y solo producen lo que falta). Útil con la cuota diaria (~96 imágenes, 10 audios).

## Criterios de aceptación
- Se puede crear un video, correr hasta el final, aprobar puertas y obtener `final.mp4` sin abrir un editor.
- Editar el guion tras generar la voz muestra "voz desactualizada"; regenerar archiva los audios anteriores y genera nuevos.
- Una edición inválida (p. ej. `beat_index` fuera de rango) no se guarda y explica el motivo.
- Cerrar el navegador durante una ejecución no la interrumpe; al volver se ve el registro y el estado.
- Cobertura ≥85 % en la parte no visual (funciones de datos/edición); las pantallas se prueban con `streamlit.testing.v1.AppTest`.

## Fuera de alcance
Login/multiusuario, publicación, métricas, subtítulos.

## Decisiones cerradas
1. Al regenerar, lo anterior se **archiva** (`stages/<etapa>/archive/<fecha>/`).
2. **Sí** hay regeneración de elementos sueltos (una imagen, una escena de voz).
3. Las claves API **se editan desde la GUI**. Como el contenedor no ve el `.env` de Windows después de arrancar, se guardan en `<carpeta de proyectos>/settings.env` (la lee la CLI y la GUI al iniciar y tiene prioridad sobre las variables de entorno). La GUI nunca muestra la clave completa (solo `••••1a2b`) y el archivo queda fuera de cualquier paquete/export. Riesgo: la clave vive en texto plano en tu carpeta de proyectos; es tu PC, pero no la subas a ningún repositorio ni nube.
