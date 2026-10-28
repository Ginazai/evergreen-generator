"""Contrato del guion: lo que `script-writer` produce y consumen los módulos siguientes."""

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from evergreen.errors import EvergreenError
from evergreen.manifest import Language

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NARRATOR = "narrator"
RHYME_LINES = (8, 60)  # de 30 s a 3 min
LONG_SCENES = (4, 10)  # de 5 a 10 min


class Character(BaseModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]
    name: Text
    visual: Text  # descripción lista para un generador de imágenes
    voice: Text  # cómo suena: edad, tono, ritmo


class Variation(BaseModel):
    seed: int
    structure: Text
    tone: Text
    twist: Text


class Section(BaseModel):
    kind: Literal["verse", "chorus", "bridge"]
    lines: list[Text] = Field(min_length=1)


class Shot(BaseModel):
    section_index: int = Field(ge=0)
    description: Text
    characters: list[str] = Field(default_factory=list)
    motion: Text | None = None  # movimiento para animar la imagen (Flow u otro)


class RhymeBody(BaseModel):
    style_prompt: Text  # estilo musical para la etapa `song`
    bpm_hint: int = Field(ge=40, le=220)
    sections: list[Section] = Field(min_length=1)
    shots: list[Shot] = Field(min_length=1)


class Beat(BaseModel):
    speaker: Text  # id de personaje o "narrator"
    text: Text
    emotion: Text


class SceneShot(BaseModel):
    beat_index: int = Field(ge=0)  # diálogo desde el que empieza la toma
    description: Text
    motion: Text | None = None


class Scene(BaseModel):
    id: Text
    setting: Text
    beats: list[Beat] = Field(min_length=1)
    visual_notes: Text
    shots: list[SceneShot] = Field(default_factory=list)  # vacío en guiones antiguos

    @model_validator(mode="after")
    def _check_shots(self):
        starts = [s.beat_index for s in self.shots]
        if self.shots and (
            starts[0] != 0
            or starts != sorted(set(starts))
            or starts[-1] >= len(self.beats)
        ):
            raise ValueError(
                f"Las tomas de la escena '{self.id}' deben empezar en el diálogo 0, ir en "
                f"orden creciente sin repetir y apuntar a diálogos que existan ({len(self.beats)})."
            )
        return self


class LongBody(BaseModel):
    logline: Text
    scenes: list[Scene] = Field(min_length=1)


class _ScriptBase(BaseModel):
    schema_version: Literal[1] = 1
    language: Language
    title: Text
    variation: Variation
    characters: list[Character] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_character_ids(self):
        ids = [c.id for c in self.characters]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay personajes con el mismo id.")
        return self

    def _check_known(self, ids: list[str], where: str) -> None:
        unknown = sorted(set(ids) - {c.id for c in self.characters})
        if unknown:
            raise ValueError(f"{where} menciona personajes que no existen: {unknown}.")


class RhymeScript(_ScriptBase):
    format: Literal["rhyme"]
    body: RhymeBody

    @model_validator(mode="after")
    def _check(self):
        lines = sum(len(s.lines) for s in self.body.sections)
        low, high = RHYME_LINES
        if not low <= lines <= high:
            raise ValueError(
                f"La rima tiene {lines} líneas; debe tener entre {low} y {high}."
            )
        for shot in self.body.shots:
            if shot.section_index >= len(self.body.sections):
                raise ValueError(
                    f"Una toma apunta a la sección {shot.section_index}, que no existe."
                )
            self._check_known(shot.characters, "Una toma")
        return self


class LongScript(_ScriptBase):
    format: Literal["long"]
    body: LongBody

    @model_validator(mode="after")
    def _check(self):
        low, high = LONG_SCENES
        scenes = self.body.scenes
        if not low <= len(scenes) <= high:
            raise ValueError(
                f"El video tiene {len(scenes)} escenas; debe tener entre {low} y {high}."
            )
        if len({s.id for s in scenes}) != len(scenes):
            raise ValueError("Hay escenas con el mismo id.")
        speakers = [b.speaker for s in scenes for b in s.beats if b.speaker != NARRATOR]
        self._check_known(speakers, "Un diálogo")
        return self


# Unión para los módulos siguientes; a Gemini se le pide el esquema del formato concreto.
Script = Annotated[RhymeScript | LongScript, Field(discriminator="format")]
_SCRIPT = TypeAdapter(Script)
_FENCE = re.compile(r"^```[A-Za-z]*[ \t]*\n(.*?)\n?```\s*$", re.DOTALL)


def clean_json(text: str) -> str:
    """Quita el BOM y las cercas ```json que los chats suelen añadir."""
    text = text.lstrip("﻿").strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _explain(error: ValidationError) -> str:
    lines = []
    for e in error.errors():
        where = ".".join(str(p) for p in e["loc"]) or "(raíz)"
        lines.append(f"- {where}: {e['msg'].removeprefix('Value error, ')}")
    return "\n".join(lines)


def parse_script(text: str, fmt: str, language: Language) -> RhymeScript | LongScript:
    """Limpia, parsea y valida una respuesta; el error dice qué falló, en español."""
    try:
        data = json.loads(clean_json(text))
    except json.JSONDecodeError as e:
        raise EvergreenError(
            f"La respuesta no es JSON válido (línea {e.lineno}, columna {e.colno}): {e.msg}."
        ) from e
    try:
        script = _SCRIPT.validate_python(data)
    except ValidationError as e:
        raise EvergreenError(f"El guion no cumple el formato:\n{_explain(e)}") from e
    if script.format != fmt or script.language != language:
        raise EvergreenError(
            f"El guion es '{script.format}' en '{script.language.value}', "
            f"pero el video es '{fmt}' en '{language.value}'."
        )
    return script


def read_script(path: Path) -> RhymeScript | LongScript:
    """Lee un `script.json` ya guardado (lo usan los módulos siguientes)."""
    return _SCRIPT.validate_python(json.loads(path.read_text(encoding="utf-8")))
