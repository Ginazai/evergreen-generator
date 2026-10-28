from datetime import datetime
from pathlib import Path

from evergreen import manifest as mf
from evergreen.errors import EvergreenError
from evergreen.registry import REVIEW_GATES, STAGES
from evergreen.slug import slugify


def create(
    title: str,
    fmt: mf.Format,
    language: mf.Language,
    root: Path,
    brief: str | None = None,
    aspect: str | None = None,
) -> Path:
    title = title.strip()
    if not title:
        raise EvergreenError("El título no puede estar vacío.")
    brief = (brief or "").strip() or None
    if brief and len(brief) > mf.BRIEF_MAX:
        raise EvergreenError(f"El tema no puede pasar de {mf.BRIEF_MAX} caracteres.")
    base = f"{slugify(title)}-{datetime.now():%Y%m%d}"
    root.mkdir(parents=True, exist_ok=True)
    n, folder = 1, root / base
    while True:  # mkdir sin exist_ok: el sufijo nunca pisa un video existente
        try:
            folder.mkdir()
            break
        except FileExistsError:
            n += 1
            folder = root / f"{base}-{n}"
    stages = STAGES[fmt.value]
    for name in stages:
        (folder / "stages" / name).mkdir(parents=True)
    mf.save(
        mf.Manifest(
            id=folder.name,
            title=title,
            format=fmt,
            language=language,
            brief=brief,
            aspect=aspect,
            created_at=datetime.now().replace(microsecond=0),
            review_gates=REVIEW_GATES[fmt.value],
            stages={name: mf.StageState() for name in stages},
        ),
        folder / "manifest.yaml",
    )
    return folder


def open_video(video_id: str, root: Path) -> Path:
    folder = root / video_id
    if not (folder / "manifest.yaml").is_file():
        raise EvergreenError(f"No existe el video '{video_id}'.")
    return folder


def list_videos(root: Path) -> list[mf.Manifest]:
    if not root.is_dir():
        return []
    return [
        mf.load(p / "manifest.yaml")
        for p in sorted(root.iterdir())
        if (p / "manifest.yaml").is_file()
    ]
