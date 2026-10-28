"""Estilo visual fijo: `style.yaml` en la carpeta de proyectos; sin él, un estilo infantil por defecto."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from evergreen.errors import EvergreenError

# En inglés a propósito: los generadores de imágenes entienden mejor el inglés.
DEFAULT_STYLE = (
    "children's picture book illustration, flat colors, soft pastel palette, "
    "friendly rounded shapes, simple uncluttered background, no text"
)
DEFAULT_NEGATIVE = "text, letters, watermark, realistic, scary, dark, blurry"


class Style(BaseModel):
    model_config = {"extra": "forbid"}
    style: str = Field(default=DEFAULT_STYLE, min_length=1)
    negative: str = DEFAULT_NEGATIVE


def load_style(root: Path) -> Style:
    path = root / "style.yaml"
    if not path.is_file():
        return Style()
    try:
        return Style.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        )
    except (yaml.YAMLError, ValidationError, UnicodeDecodeError) as e:
        raise EvergreenError(f"style.yaml no es válido: {e}") from e
