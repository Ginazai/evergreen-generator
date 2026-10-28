import copy
import json
from datetime import datetime

import pytest

from evergreen.manifest import Format, Language, Manifest
from evergreen.script_writer.models import parse_script
from evergreen.script_writer.prompts import build_prompt, example_data
from evergreen.script_writer.variation import pick_variation

VARIATION = pick_variation("rhyme", seed=3)


def manifest(fmt, language, brief="patitos que aprenden a nadar"):
    return Manifest(
        id="x",
        title="Los patitos",
        format=fmt,
        language=language,
        brief=brief,
        created_at=datetime(2026, 10, 21),
    )


CASES = [(f, lang) for f in Format for lang in Language]


@pytest.mark.parametrize(("fmt", "language"), CASES)
def test_prompt_has_everything_the_model_needs(fmt, language):
    prompt = build_prompt(manifest(fmt, language), VARIATION)
    name = {"es": "español", "en": "inglés"}[language.value]
    for expected in (
        "Los patitos",
        "patitos que aprenden a nadar",
        f"contenido del guion: {name}",
        VARIATION.structure,
        VARIATION.tone,
        VARIATION.twist,
        f'"format": "{fmt.value}"',
        f'"language": "{language.value}"',
    ):
        assert expected in prompt
    assert ("style_prompt" in prompt) == (fmt == Format.rhyme)
    assert ("scenes" in prompt) == (fmt == Format.long)


def test_without_brief_there_are_no_gaps_or_none():
    prompt = build_prompt(manifest(Format.rhyme, Language.es, brief=None), VARIATION)
    assert "None" not in prompt and "Tema o notas" not in prompt


def test_prompt_demands_original_content_without_brands():
    prompt = build_prompt(manifest(Format.rhyme, Language.es), VARIATION)
    assert "Contenido original" in prompt and "marcas" in prompt


def test_prompt_contains_no_secrets_from_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    assert "fake-key-123" not in build_prompt(
        manifest(Format.long, Language.en), VARIATION
    )


@pytest.mark.parametrize(("fmt", "language"), CASES)
def test_example_follows_the_contract(fmt, language):
    """Si el contrato cambia y el ejemplo no, esta prueba lo detecta."""
    data = copy.deepcopy(example_data(fmt, manifest(fmt, language), VARIATION))
    body = data["body"]
    if fmt == Format.rhyme:  # se sustituyen los marcadores y se cumplen los mínimos
        body["sections"] = [{"kind": "verse", "lines": ["a"] * 12}]
    else:
        scene = body["scenes"][0]
        scene["beats"][0]["speaker"] = "personaje-1"
        body["scenes"] = [{**scene, "id": f"e{n}"} for n in range(4)]
    script = parse_script(json.dumps(data), fmt.value, language)
    assert script.variation == VARIATION
