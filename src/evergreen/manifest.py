import os
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from evergreen import fsutil

BRIEF_MAX = 500


class Format(str, Enum):
    rhyme = "rhyme"
    long = "long"


class Language(str, Enum):
    es = "es"
    en = "en"


Aspect = Literal["16:9", "9:16"]


class Status(str, Enum):
    pending = "pending"
    running = "running"
    awaiting_manual = "awaiting_manual"
    awaiting_approval = "awaiting_approval"
    done = "done"
    failed = "failed"


class StageState(BaseModel):
    # extra="forbid": un campo no declarado (p. ej. una clave) no entra al manifest.
    model_config = ConfigDict(extra="forbid")

    status: Status = Status.pending
    adapter: str = "manual"
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None
    stale: bool = False  # lo que alimenta a esta etapa cambió después de generarla


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    id: str
    title: str = Field(min_length=1)
    format: Format
    language: Language = Language.es
    brief: str | None = Field(default=None, max_length=BRIEF_MAX)
    aspect: Aspect | None = None  # None = el de por defecto del formato
    created_at: datetime
    review_gates: list[str] = Field(default_factory=list)
    stages: dict[str, StageState] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _gates_are_stages(self) -> "Manifest":
        unknown = set(self.review_gates) - set(self.stages)
        if unknown:
            raise ValueError(f"Puertas de aprobación sin etapa: {sorted(unknown)}")
        return self


DEFAULT_ASPECT = {Format.long: "16:9", Format.rhyme: "9:16"}


def aspect_of(manifest: Manifest) -> str:
    """Proporción efectiva: la elegida al crear el video o la de por defecto del formato."""
    return manifest.aspect or DEFAULT_ASPECT[manifest.format]


def load(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def save(manifest: Manifest, path: Path) -> None:
    text = yaml.safe_dump(
        manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False
    )
    # Temporal en la misma carpeta: os.replace entre carpetas puede fallar en bind mounts.
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        fsutil.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
