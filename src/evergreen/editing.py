"""Ediciones que hace la GUI (o quien sea): validan con los modelos del núcleo, guardan atómico y marcan lo desactualizado."""

import os
import tempfile
from pathlib import Path

from evergreen import fsutil, project
from evergreen import manifest as mf
from evergreen.errors import EvergreenError
from evergreen.reopen import CONFIG_AFFECTS, DOWNSTREAM, mark_stale
from evergreen.script_writer.cast import apply_cast, load_cast
from evergreen.script_writer.models import parse_script
from evergreen.script_writer.render import render_markdown
from evergreen.visuals.style import load_style
from evergreen.voice_audio.voices import load_voices

LOADERS = {"cast": load_cast, "voices": load_voices, "style": load_style}


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        fsutil.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _save_manifest_with_stale(
    video_dir: Path, manifest: mf.Manifest, stages: list[str]
) -> list[str]:
    marked = mark_stale(manifest, stages)
    mf.save(manifest, video_dir / "manifest.yaml")
    return marked


def set_title_and_brief(video_dir: Path, title: str, brief: str | None) -> list[str]:
    """Cambiar el tema deja desactualizado el guion y todo lo que sale de él."""
    title, brief = title.strip(), (brief or "").strip() or None
    if not title:
        raise EvergreenError("El título no puede estar vacío.")
    if brief and len(brief) > mf.BRIEF_MAX:
        raise EvergreenError(f"El tema no puede pasar de {mf.BRIEF_MAX} caracteres.")
    manifest = mf.load(video_dir / "manifest.yaml")
    changed = brief != manifest.brief
    manifest.title, manifest.brief = title, brief
    stages = ["script", *DOWNSTREAM[manifest.format.value]["script"]] if changed else []
    return _save_manifest_with_stale(video_dir, manifest, stages)


def save_script(video_dir: Path, text: str) -> list[str]:
    """Valida el JSON del guion (y el elenco, si hay cast.yaml); reescribe script.json y script.md."""
    manifest = mf.load(video_dir / "manifest.yaml")
    stage_dir = video_dir / "stages" / "script"
    if not (stage_dir / "script.json").is_file():
        raise EvergreenError(
            "Aún no hay guion: genera la etapa `script` antes de editarlo."
        )
    script = parse_script(text, manifest.format.value, manifest.language)
    cast = load_cast(video_dir.parent)
    if cast:
        script = apply_cast(script, cast)
    atomic_write(
        stage_dir / "script.json", script.model_dump_json(indent=2, exclude_none=True)
    )
    atomic_write(stage_dir / "script.md", render_markdown(script))
    return _save_manifest_with_stale(
        video_dir, manifest, DOWNSTREAM[manifest.format.value]["script"]
    )


def save_config(root: Path, kind: str, text: str) -> dict[str, list[str]]:
    """Guarda cast/voices/style.yaml del proyecto y marca los videos que los usan. Devuelve {video: etapas}."""
    if kind not in LOADERS:
        raise EvergreenError(f"No sé editar '{kind}'.")
    with (
        tempfile.TemporaryDirectory() as tmp
    ):  # los cargadores leen `<carpeta>/<tipo>.yaml`
        probe = Path(tmp)
        (probe / f"{kind}.yaml").write_text(text, encoding="utf-8")
        LOADERS[kind](probe)
    atomic_write(root / f"{kind}.yaml", text)
    affected = {}
    for m in project.list_videos(root):
        marked = _save_manifest_with_stale(
            root / m.id, m, CONFIG_AFFECTS[kind][m.format.value]
        )
        if marked:
            affected[m.id] = marked
    return affected
