# Evergreen: generador de contenido

Organiza la producción de videos evergreen (rimas infantiles y videos largos con guion y personajes) en etapas: cada video vive en su propia carpeta, se puede **reanudar** si algo se corta y cada etapa se hace con una API o **a mano**, según lo que tengas disponible.

> Estado: `core-pipeline` y `script-writer`. El motor, el modo manual y el guion (con Gemini o a mano) funcionan; la voz, las imágenes y el montaje llegan con los módulos siguientes. Hoy se usa por línea de comandos.

## Requisitos

- Windows 10/11 con **Docker Desktop** abierto. No necesitas instalar Python ni ffmpeg.

## Configuración (una vez)

1. Copia `.env.example` a `.env`.
2. En `.env`, pon la carpeta de Windows donde quieres tus videos, con barras normales y sin comillas:
   `EVERGREEN_PROJECTS_DIR=D:/Videos`
   Créala antes si no existe. Si omites esta línea, se usa la carpeta `projects` junto al programa.
3. Doble clic en `iniciar.bat`. Construye la imagen y te deja en una terminal donde escribes los comandos de abajo **sin** el prefijo largo de Docker.

Sin `iniciar.bat`, antepón `docker compose run --rm app` a cada comando (ejemplo: `docker compose run --rm app evergreen list`).

## Uso

```
evergreen new "Los patitos" --format rhyme      # crea el video; imprime su id
evergreen new "Aventura" --format long --language en
evergreen new "Los patitos" --format rhyme --brief "patitos que aprenden a nadar"   # tema opcional (máx. 500 caracteres)
evergreen run los-patitos-20261020              # ejecuta o reanuda
evergreen status los-patitos-20261020           # estado de cada etapa
evergreen approve los-patitos-20261020 script   # aprueba una etapa en pausa
evergreen list                                  # todos los videos
```

El **id** es el nombre de la carpeta del video y lo imprime `new`. Si creas dos videos con el mismo título el mismo día, el segundo termina en `-2`.

### Formatos y etapas

| Formato | Etapas | Pausa para aprobar |
|---|---|---|
| `rhyme` | script → song → visuals → assembly | script, song |
| `long` | script → voice → music → characters → scenes → assembly | script, voice, characters, scenes |

Idioma por video: `--language es` (por defecto) o `--language en`.

### Pasos manuales

Si una etapa no tiene API, `run` se detiene y escribe `stages/<etapa>/MANUAL.md` dentro de la carpeta del video con los archivos que debes generar. Déjalos en `stages/<etapa>/inbox/` y vuelve a ejecutar `run`: continúa solo.

### Aprobaciones

En las etapas con pausa, `run` termina la etapa y se detiene en "esperando aprobación". Revisa el resultado y, si está bien, `approve`, luego `run`. Así no gastas créditos de la etapa siguiente sin haber revisado.

### Si algo falla o se corta

Vuelve a ejecutar `run`. Las etapas terminadas no se repiten; solo se reintenta la que falló o quedó a medias.

## El guion (etapa `script`)

Es la primera etapa de cada video. Produce `stages/script/script.json` (lo leen las etapas siguientes) y `script.md` (para que lo revises). Cada video recibe una **variación** distinta (estructura, tono y un giro), y si el guion se parece demasiado a uno anterior se descarta y se regenera.

**Con Gemini** (si `GEMINI_API_KEY` tiene valor en `.env`): `run` genera el guion solo. Hasta 6 llamadas por ejecución, con reintentos ante límite de uso.

**A mano** (si no hay clave, o con `EVERGREEN_SCRIPT_MODE=manual`): `run` escribe `stages/script/MANUAL.md` con el prompt completo. Pégalo en el chat que prefieras, guarda la respuesta como `stages/script/inbox/script.json` (en el Bloc de notas: Guardar como > Todos los archivos) y vuelve a ejecutar `run`. Si el archivo tiene un problema, `MANUAL.md` te dice cuál.

Tras el guion el pipeline **se detiene para que lo apruebes** (`evergreen approve <id> script`): revisar un guion es gratis y evita gastar créditos de audio en uno malo.

| Variable (`.env`) | Para qué sirve | Por defecto |
|---|---|---|
| `GEMINI_API_KEY` | Clave de Google AI Studio. Vacía = modo manual | vacía |
| `GEMINI_MODEL` | Modelo de Gemini | `gemini-3.5-flash-lite` |
| `EVERGREEN_SCRIPT_MODE` | `manual` fuerza el modo manual aunque haya clave | vacío |
| `EVERGREEN_SIMILARITY_THRESHOLD` | Umbral de parecido entre guiones (0 a 1) | `0.35` |

**Si se agota la cuota gratuita:** la etapa queda "falló" con un mensaje. La cuota diaria se reinicia a medianoche (hora del Pacífico). Vuelve a ejecutar `run` más tarde, o pasa a modo manual. Límites medidos en AI Studio (2026-10-22): `gemini-3.5-flash-lite` 15 solicitudes/min y 500/día; `gemini-3.8-flash` 5/min y solo 20/día (alcanza para ~3 videos, porque una ejecución puede gastar hasta 6 llamadas).

**Privacidad:** en el tier gratuito de la API de Gemini, Google puede usar lo que envías (título, tema, idioma) para mejorar sus productos. Los guiones de tus otros videos nunca se envían: la comprobación de parecido se hace en tu PC.

## Claves de API

Se guardan solo en `.env` (nunca en el manifest, ni en la salida del programa, ni en los archivos de cada video). `.env` está excluido del repositorio.

## Desarrollo

```
docker compose run --rm app pytest --cov=evergreen --cov-report=term-missing
docker compose run --rm app ruff check .
```

Más detalle: `SPEC-core-pipeline.md` y `tasks/plan.md`.

## Problemas frecuentes

- **"Gemini rechazó la solicitud por límite de uso"**: ver la sección del guion; vuelve a ejecutar `run` más tarde o usa `EVERGREEN_SCRIPT_MODE=manual`.
- **`run` sigue pidiendo el guion aunque ya lo guardaste**: revisa que esté en `stages\script\inbox\` y, en el Bloc de notas, elige Tipo: "Todos los archivos" al guardar. Si quedó como `script.json.txt`, también se acepta.
- **"No existe el video"**: revisa que el id sea exacto (`evergreen list` los muestra) y que `docker-compose.yml` tenga `EVERGREEN_PROJECTS_DIR: /data/projects` en `environment`.
- **"error during connect" o similar**: Docker Desktop no está abierto.
- **La carpeta de videos aparece vacía**: confirma la ruta en `.env` y que Docker Desktop tenga acceso a esa unidad (Settings → Resources → File sharing).

## Elenco fijo (`cast.yaml`)

Para que los personajes se repitan entre videos, copia `cast.example.yaml` como `cast.yaml` en tu carpeta de proyectos y edítalo. Si existe, el prompt pide usar solo esos personajes y el programa fija su nombre, aspecto y voz; un guion con otros ids se rechaza (en modo manual, el motivo aparece en `MANUAL.md`). Sin el archivo, el modelo inventa los personajes de cada video.

## El audio (etapas `voice`, `song` y `music`)

**Voz de los videos largos (`voice`).** Modo según `EVERGREEN_VOICE_MODE`: `gemini` (por defecto si hay `GEMINI_API_KEY`), `piper` (voz local, sin cuota) o `manual`. Genera un WAV por escena y un `timeline.json` en `stages/voice/`.
- **Cuota:** la voz de Gemini gratuita permite unas **10 peticiones al día** y 3 por minuto (tu cuenta, AI Studio). Un video usa una petición por escena (más si una escena tiene más de 2 voces). Si se agota, la etapa falla diciendo cuántos audios hizo; al volver a ejecutar `evergreen run <id>` retoma donde quedó.
- **Piper:** la primera vez descarga la voz (necesita internet) y la guarda en `_piper/` dentro de tu carpeta de proyectos. Todos los personajes suenan igual. `PIPER_VOICE` cambia la voz (por defecto `es_ES-davefx-medium` / `en_US-lessac-medium`).
- **Voces de los personajes:** copia `voices.example.yaml` como `voices.yaml` en tu carpeta de proyectos. Sin él se usan voces por defecto estables (el mismo personaje suena igual en todos los videos).

**Canción (`song`, rimas) y música de fondo (`music`).** Siempre manuales: no hay vía gratuita por API. `run` deja un `MANUAL.md` con la letra y el estilo (o la descripción de la música) listos para pegar en el generador que uses; guarda el resultado como `song.mp3`/`song.wav` (o `music.mp3`/`music.wav`) en `stages/<etapa>/inbox/` y vuelve a ejecutar.

**Privacidad:** con la voz de Gemini gratuita, el texto de los diálogos se envía a Google, que puede usarlo para mejorar sus productos.

## Las imágenes (etapas `visuals`, `characters` y `scenes`)

Qué se genera: **rima** → etapa `visuals` (una hoja por personaje y una imagen por toma, en 9:16); **video largo** → `characters` (una hoja por personaje, que apruebas) y `scenes` (varias imágenes por escena, en 16:9). Con `evergreen new --aspect 9:16` (o `16:9`) cambias la proporción de un video.

- **Cloudflare (gratis):** pon `CLOUDFLARE_ACCOUNT_ID` y `CLOUDFLARE_API_TOKEN` en `.env` (cuenta gratuita; el token con permiso de Workers AI). Modelo FLUX.2 klein 4B: ≈ 104 neuronas por imagen medidas; con 10 000 neuronas diarias salen unas 96 imágenes al día. Las escenas usan la hoja del personaje como **imagen de referencia** para que se parezca entre imágenes. Si la cuota se acaba, la etapa falla diciendo cuántas hizo y al volver a ejecutar retoma; o pasa a manual con `EVERGREEN_IMAGE_MODE=manual` (solo lista las que faltan).
- **Manual:** sin credenciales, `run` deja un `MANUAL.md` con un prompt por imagen. Guarda cada una en `stages/<etapa>/inbox/` como `<clave>.png` o `.jpg`.
- **Clips con Google Flow (opcional):** el `MANUAL.md` incluye un prompt de movimiento por imagen; en Flow, "Frames to Video" con la imagen como primer cuadro; guarda el clip como `<clave>.mp4` en `inbox/`. Marca ★ las imágenes que más lo merecen (≈ 5 clips al día gratis). El montaje usa el clip si existe y, si no, zoom lento.
- **Estilo:** copia `style.example.yaml` como `style.yaml` en tu carpeta de proyectos. Sin él se usa un estilo infantil plano.
- **Privacidad y licencia:** los prompts (estilo + descripciones + escena) viajan a Cloudflare. Lee los términos de Black Forest Labs (FLUX.2 klein) antes de monetizar.

## Montaje (assembly)

`evergreen run` termina con la etapa `assembly`: junta las imágenes (o los clips `inbox/<clave>.mp4` de Flow, si existen), la voz + música (long) o la canción (rhyme) y deja `stages/assembly/final.mp4` (1080p, 16:9 o 9:16 según el video) y `assembly.json`.
Movimiento: zoom/paneo suave en cada imagen; fundido cruzado entre tomas y entrada/salida a negro entre escenas. Audio: la música baja cuando habla la voz, y todo se normaliza a −14 LUFS. Sin subtítulos en esta versión.
Es reanudable: las tomas ya renderizadas (`stages/assembly/work/`) no se repiten. Para añadir un clip de Flow, déjalo como `stages/scenes/inbox/<clave>.mp4` y vuelve a ejecutar la etapa.

## Interfaz web (GUI)

`docker compose up gui` y abre http://localhost:8501 (solo accesible desde tu PC).
Desde ahí: crear videos, ejecutar/continuar (en segundo plano; puedes cerrar la pestaña), aprobar, subir archivos de pasos manuales, ver guion/audio/imágenes/video, y editar título, tema, guion, `cast.yaml`, `voices.yaml`, `style.yaml` y las claves (se guardan en `<proyectos>/settings.env`, en texto plano: no lo subas a ningún repositorio).
Al cambiar algo aguas arriba, las etapas que dependen de ello se marcan **desactualizadas**; elige *Rehacer* (archiva lo anterior en `stages/<etapa>/archive/`) o *Mantener*. *Regenerar N y ejecutar* rehace solo los audios o imágenes que elijas (varios a la vez, también mientras la etapa espera aprobación); los demás ni se tocan ni gastan cuota. Lo mismo desde la CLI: `evergreen reopen <video> <etapa>`.
