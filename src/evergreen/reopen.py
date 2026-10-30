"""Reabrir etapas y marcar lo que quedó desactualizado. Nada se borra: lo anterior se archiva."""

import re
import shutil
from datetime import datetime
from pathlib import Path

from evergreen import manifest as mf
from evergreen.errors import EvergreenError

# etapa -> etapas que se alimentan de ella (el montaje depende de todo)
DOWNSTREAM = {
    "long": {
        "script": ["voice", "music", "characters", "scenes", "assembly"],
        "voice": ["assembly"],
        "music": ["assembly"],
        "characters": ["scenes", "assembly"],
        "scenes": ["assembly"],
        "assembly": [],
    },
    "rhyme": {
        "script": ["song", "visuals", "assembly"],
        "song": ["assembly"],
        "visuals": ["assembly"],
        "assembly": [],
    },
}
# archivo de configuración compartido -> etapas que lo usan, por formato
CONFIG_AFFECTS = {
    "cast": {"long": ["characters", "scenes"], "rhyme": ["visuals"]},
    "style": {"long": ["characters", "scenes"], "rhyme": ["visuals"]},
    "voices": {"long": ["voice"], "rhyme": []},
}
KEEP_IN_PLACE = {"archive", "work"}  # `work` es caché por hash: no se archiva


def archive_files(stage_dir: Path, files: list[Path]) -> Path | None:
    """Mueve los archivos a `archive/<fecha>/` conservando su ruta relativa."""
    files = [f for f in files if f.exists()]
    if not files:
        return None
    base = stage_dir / "archive" / f"{datetime.now():%Y%m%d-%H%M%S}"
    dest, n = base, 1
    while dest.exists():
        n += 1
        dest = base.with_name(f"{base.name}-{n}")
    for f in files:
        target = dest / f.relative_to(stage_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(f, target)
    return dest


def _state(manifest: mf.Manifest, stage: str) -> mf.StageState:
    state = manifest.stages.get(stage)
    if state is None:
        raise EvergreenError(f"El video no tiene la etapa '{stage}'.")
    return state


def mark_stale(manifest: mf.Manifest, stages: list[str]) -> list[str]:
    """Marca como desactualizadas las etapas que ya tenían resultado. Devuelve cuáles."""
    marked = []
    for name in stages:
        state = manifest.stages.get(name)
        if state and state.status in (mf.Status.done, mf.Status.awaiting_approval):
            state.stale = True
            marked.append(name)
    return marked


def reopen(video_dir: Path, stage: str) -> list[str]:
    """La etapa vuelve a `pending` con sus archivos archivados; las que dependen de ella quedan `stale`."""
    path = video_dir / "manifest.yaml"
    manifest = mf.load(path)
    state = _state(manifest, stage)
    if state.status == mf.Status.running:
        raise EvergreenError(f"La etapa '{stage}' se está ejecutando.")
    stage_dir = video_dir / "stages" / stage
    if stage_dir.is_dir():
        archive_files(
            stage_dir, [p for p in stage_dir.iterdir() if p.name not in KEEP_IN_PLACE]
        )
    manifest.stages[stage] = mf.StageState(adapter=state.adapter)
    marked = mark_stale(manifest, DOWNSTREAM[manifest.format.value][stage])
    mf.save(manifest, path)
    return marked


def keep(video_dir: Path, stage: str) -> None:
    """El usuario decide conservar una etapa desactualizada."""
    path = video_dir / "manifest.yaml"
    manifest = mf.load(path)
    _state(manifest, stage).stale = False
    mf.save(manifest, path)


KEY = re.compile(r"^[a-z0-9-]+$")


def regenerate_items(video_dir: Path, stage: str, keys: list[str]) -> list[str]:
    """Archiva solo los archivos de esos elementos (`<clave>.*`) y deja la etapa pendiente: al correrla,
    los adaptadores (reanudables) producen solo lo que falta. Devuelve las etapas que quedan desactualizadas.
    Todo o nada: si una clave no existe no se archiva ninguna."""
    path = video_dir / "manifest.yaml"
    manifest = mf.load(path)
    state = _state(manifest, stage)
    if state.status == mf.Status.running:
        raise EvergreenError(f"La etapa '{stage}' se está ejecutando.")
    if not keys:
        raise EvergreenError("Elige al menos un elemento.")
    stage_dir = video_dir / "stages" / stage
    files = []
    for key in dict.fromkeys(keys):
        found = (
            [p for d in (stage_dir, stage_dir / "inbox") for p in d.glob(f"{key}.*")]
            if KEY.match(key)
            else []
        )
        if not found:
            raise EvergreenError(f"No encuentro '{key}' en la etapa '{stage}'.")
        files += found
    archive_files(stage_dir, files)
    manifest.stages[stage] = mf.StageState(adapter=state.adapter)
    marked = mark_stale(manifest, DOWNSTREAM[manifest.format.value][stage])
    mf.save(manifest, path)
    return marked


def regenerate_item(video_dir: Path, stage: str, key: str) -> list[str]:
    return regenerate_items(video_dir, stage, [key])
