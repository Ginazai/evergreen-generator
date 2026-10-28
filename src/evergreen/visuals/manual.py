"""Paso manual de las etapas visuales: PROMPTS.md con un prompt por imagen y, opcionalmente, clips."""

import json
from pathlib import Path

from evergreen import manifest as mf
from evergreen.adapters.base import Done, NeedsManual, StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script
from evergreen.visuals.prompts import ImageRequest, plan_images
from evergreen.visuals.style import load_style

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
CLIP_EXTENSION = ".mp4"

HEADER = """# Paso manual: {stage}

Video: {title} (proporción {aspect})

## Qué hacer

1. Genera cada imagen con el generador que prefieras usando su prompt (más abajo) y la proporción {aspect}.
2. Guarda cada una en `stages/{stage}/inbox/` con el nombre de su clave y extensión `.png` o `.jpg` (por ejemplo `{example}.png`).
3. (Opcional) Para animar una imagen: en Google Flow elige "Frames to Video", sube la imagen como primer cuadro,
   pega el prompt de movimiento, genera (8 s) y guarda el clip como `<clave>.mp4` en la misma carpeta.
   Los créditos gratuitos diarios (≈ 5 clips) no se acumulan: empieza por las marcadas con ★.
4. Ejecuta `evergreen run {id}`.
{problem}
## Imágenes

"""


def find_file(inbox: Path, key: str, extensions) -> Path | None:
    return next((p for e in extensions if (p := inbox / f"{key}{e}").is_file()), None)


def build_text(
    ctx: StageContext, requests: list[ImageRequest], aspect: str, problem
) -> str:
    m = ctx.manifest
    out = [
        HEADER.format(
            stage=ctx.stage,
            title=m.title,
            aspect=aspect,
            example=requests[0].key,
            id=m.id,
            problem=f"\n## Problema\n\n{problem}\n" if problem else "",
        )
    ]
    for r in requests:
        star = " ★" if r.priority else ""
        out.append(f"### {r.key}{star}\n\n````text\n{r.prompt}\n````\n")
        if r.negative:
            out.append(f"Evitar: {r.negative}\n")
        if r.motion:
            out.append(f"Movimiento (Flow): {r.motion}\n")
    return "\n".join(out)


def collect(ctx: StageContext, requests: list[ImageRequest], aspect: str):
    """Devuelve (entradas de images.json, claves que faltan, problema o None)."""
    inbox = ctx.stage_dir / "inbox"
    entries, missing, problem = [], [], None
    for r in requests:
        # Las imágenes generadas por API viven en la carpeta de la etapa; las manuales, en inbox/.
        image = find_file(ctx.stage_dir, r.key, IMAGE_EXTENSIONS) or find_file(
            inbox, r.key, IMAGE_EXTENSIONS
        )
        if image is None:
            missing.append(r.key)
            continue
        if image.stat().st_size == 0:
            problem = f"`{image.name}` está vacío. Genera la imagen de nuevo."
            missing.append(r.key)
            continue
        clip = find_file(inbox, r.key, (CLIP_EXTENSION,))
        if clip is not None and clip.stat().st_size == 0:
            clip = None
        entries.append(
            {
                "key": r.key,
                "image": image.relative_to(ctx.stage_dir).as_posix(),
                "clip": f"inbox/{clip.name}" if clip else None,
                "prompt": r.prompt,
                "motion": r.motion,
                "aspect": aspect,
            }
        )
    return entries, missing, problem


def finish(ctx: StageContext, entries: list[dict]) -> Done:
    images_json = ctx.stage_dir / "images.json"
    images_json.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    files = [ctx.stage_dir / e["image"] for e in entries]
    files += [ctx.stage_dir / e["clip"] for e in entries if e["clip"]]
    return Done([*files, images_json])


class ImageManualAdapter:
    name = "manual"

    def run(self, ctx: StageContext) -> StageResult:
        script_path = ctx.video_dir / "stages" / "script" / "script.json"
        if not script_path.is_file():
            raise EvergreenError(
                "No encuentro el guion: ejecuta primero la etapa `script`."
            )
        script = read_script(script_path)
        try:
            requests = plan_images(ctx.stage, script, load_style(ctx.video_dir.parent))
        except ValueError as e:
            raise EvergreenError(str(e)) from e
        aspect = mf.aspect_of(ctx.manifest)
        (ctx.stage_dir / "inbox").mkdir(parents=True, exist_ok=True)

        entries, missing, problem = collect(ctx, requests, aspect)
        manual_md = ctx.stage_dir / "MANUAL.md"
        if not missing:
            manual_md.unlink(missing_ok=True)
            return finish(ctx, entries)
        manual_md.write_text(
            build_text(ctx, requests, aspect, problem), encoding="utf-8"
        )
        return NeedsManual(manual_md, [f"{k}.png" for k in missing])
