"""Elenco fijo: `cast.yaml` en la carpeta de proyectos. Si existe, manda el código, no el modelo."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from evergreen.errors import EvergreenError
from evergreen.script_writer.models import Character


class Cast(BaseModel):
    characters: list[Character]


def load_cast(root: Path) -> list[Character] | None:
    path = root / "cast.yaml"
    if not path.is_file():
        return None
    try:
        cast = Cast.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError, UnicodeDecodeError) as e:
        raise EvergreenError(f"cast.yaml no es válido: {e}") from e
    ids = [c.id for c in cast.characters]
    if not ids or len(set(ids)) != len(ids):
        raise EvergreenError("cast.yaml debe tener personajes con ids distintos.")
    return cast.characters


def apply_cast(script, cast: list[Character]):
    """Rechaza ids fuera del elenco y fija nombre, aspecto y voz tal como están en cast.yaml."""
    by_id = {c.id: c for c in cast}
    unknown = [c.id for c in script.characters if c.id not in by_id]
    if unknown:
        raise EvergreenError(
            f"El guion usa personajes que no están en cast.yaml: {', '.join(unknown)}. "
            f"Disponibles: {', '.join(by_id)}."
        )
    return script.model_copy(
        update={"characters": [by_id[c.id] for c in script.characters]}
    )
