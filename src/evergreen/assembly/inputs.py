"""Localiza y valida lo que producen las etapas anteriores. Cada falta nombra el archivo y la etapa."""

import json
from dataclasses import dataclass
from pathlib import Path

from evergreen import manifest as mf
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script

AUDIO_EXTENSIONS = (".wav", ".mp3")


@dataclass(frozen=True)
class Frame:
    key: str
    image: Path
    clip: Path | None  # clip de Flow (`<clave>.mp4`), si existe y no está vacío


@dataclass(frozen=True)
class Inputs:
    script: object
    aspect: str
    voice_files: list[Path]  # long: en orden de reproducción
    scene_seconds_files: dict[
        str, list[Path]
    ]  # long: archivos de cada escena (con timeline.json)
    music: Path | None
    song: Path | None
    frames: dict[str, Frame]


def _outputs(video_dir: Path, manifest: mf.Manifest, stage: str) -> list[Path]:
    state = manifest.stages.get(stage)
    if state is None or state.status not in (
        mf.Status.done,
        mf.Status.awaiting_approval,
    ):
        raise EvergreenError(
            f"La etapa `{stage}` aún no está terminada: ejecútala antes del montaje."
        )
    paths = [video_dir / o for o in state.outputs]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise EvergreenError(
            f"Falta el archivo {missing[0].name} de la etapa `{stage}`."
        )
    return paths


def _audio(video_dir, manifest, stage) -> list[Path]:
    files = [
        p
        for p in _outputs(video_dir, manifest, stage)
        if p.suffix.lower() in AUDIO_EXTENSIONS
    ]
    if not files:
        raise EvergreenError(f"La etapa `{stage}` no dejó ningún audio (.wav o .mp3).")
    empty = [p for p in files if p.stat().st_size == 0]
    if empty:
        raise EvergreenError(
            f"El audio {empty[0].name} de la etapa `{stage}` está vacío."
        )
    return files


def _frames(video_dir: Path, stage: str) -> dict[str, Frame]:
    stage_dir = video_dir / "stages" / stage
    index = stage_dir / "images.json"
    if not index.is_file():
        raise EvergreenError(f"Falta images.json de la etapa `{stage}`.")
    frames = {}
    for entry in json.loads(index.read_text(encoding="utf-8")):
        image = stage_dir / entry["image"]
        if not image.is_file() or image.stat().st_size == 0:
            raise EvergreenError(
                f"Falta la imagen {entry['image']} de la etapa `{stage}`."
            )
        # Los clips se hacen después de las imágenes: se buscan ahora, no solo en images.json.
        clip = stage_dir / "inbox" / f"{entry['key']}.mp4"
        frames[entry["key"]] = Frame(
            entry["key"],
            image,
            clip if clip.is_file() and clip.stat().st_size > 0 else None,
        )
    return frames


def load_inputs(video_dir: Path, manifest: mf.Manifest) -> Inputs:
    script_path = video_dir / "stages" / "script" / "script.json"
    if not script_path.is_file():
        raise EvergreenError("Falta script.json de la etapa `script`.")
    script = read_script(script_path)
    aspect = mf.aspect_of(manifest)

    if script.format == "rhyme":
        song = _audio(video_dir, manifest, "song")[0]
        return Inputs(script, aspect, [], {}, None, song, _frames(video_dir, "visuals"))

    voice_outputs = _outputs(video_dir, manifest, "voice")
    voice = _audio(video_dir, manifest, "voice")
    per_scene: dict[str, list[Path]] = {}
    timeline = next((p for p in voice_outputs if p.name == "timeline.json"), None)
    if (
        timeline is not None
    ):  # voz por API o Piper: un archivo por escena (o parte de escena)
        for entry in json.loads(timeline.read_text(encoding="utf-8")):
            per_scene.setdefault(entry["scene_id"], []).append(
                timeline.parent / entry["file"]
            )
        voice = [f for files in per_scene.values() for f in files]
    music = _audio(video_dir, manifest, "music")[0]
    return Inputs(
        script, aspect, voice, per_scene, music, None, _frames(video_dir, "scenes")
    )
