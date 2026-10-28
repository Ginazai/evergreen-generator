"""Mapa de voces: `voices.yaml` en la carpeta de proyectos; sin él, voces por defecto estables."""

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from evergreen.errors import EvergreenError

NARRATOR = "narrator"
DEFAULT_NARRATOR = "Charon"
# Nombres de voces predefinidas de Gemini. Solo Kore y Puck salen en la documentación leída;
# el resto no se verificó: si la API rechaza alguno, cámbialo en voices.yaml.
POOL = ["Kore", "Puck", "Zephyr", "Fenrir", "Aoede", "Leda", "Orus"]


class Voices(BaseModel):
    model_config = {"extra": "forbid"}
    narrator: str = Field(default=DEFAULT_NARRATOR, min_length=1)
    characters: dict[str, str] = Field(default_factory=dict)


def load_voices(root: Path) -> Voices:
    path = root / "voices.yaml"
    if not path.is_file():
        return Voices()
    try:
        return Voices.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        )
    except (yaml.YAMLError, ValidationError, UnicodeDecodeError) as e:
        raise EvergreenError(f"voices.yaml no es válido: {e}") from e


def _start(character_id: str) -> int:
    # sha256 y no hash(): hash() cambia entre ejecuciones y la voz no sería estable.
    return int(hashlib.sha256(character_id.encode()).hexdigest(), 16) % len(POOL)


def assign(character_ids: list[str], voices: Voices) -> dict[str, str]:
    """Voz de cada personaje (y del narrador). Las del archivo mandan; el resto, por id estable.

    Las voces por defecto no se repiten dentro de un mismo video mientras la reserva alcance.
    """
    result = {NARRATOR: voices.narrator}
    used = {voices.narrator, *voices.characters.values()}
    for cid in sorted(set(character_ids)):
        if cid in voices.characters:
            result[cid] = voices.characters[cid]
            continue
        start = _start(cid)
        order = [POOL[(start + k) % len(POOL)] for k in range(len(POOL))]
        free = next((v for v in order if v not in used), order[0])
        used.add(free)
        result[cid] = free
    return result
