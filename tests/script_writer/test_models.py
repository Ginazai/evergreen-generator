import json

import pytest
from script_samples import long_data, rhyme_data

from evergreen.errors import EvergreenError
from evergreen.manifest import Language
from evergreen.script_writer.models import (
    LongScript,
    RhymeScript,
    clean_json,
    parse_script,
)

ES = Language.es


def parse(data, fmt="rhyme", language=ES):
    return parse_script(json.dumps(data, ensure_ascii=False), fmt, language)


def test_valid_scripts_round_trip_losslessly():
    for data, fmt, cls in [
        (rhyme_data(), "rhyme", RhymeScript),
        (long_data(), "long", LongScript),
    ]:
        script = parse(data, fmt)
        assert isinstance(script, cls)
        assert script.model_dump(mode="json") == data


def mutate(fn, base=rhyme_data):
    data = base()
    fn(data)
    return data


@pytest.mark.parametrize(
    ("data", "fmt", "message"),
    [
        (
            mutate(lambda d: d["body"]["shots"][0].update(characters=["fantasma"])),
            "rhyme",
            "no existen",
        ),
        (
            mutate(
                lambda d: d["body"]["sections"].append({"kind": "verse", "lines": []})
            ),
            "rhyme",
            "lines",
        ),
        (
            mutate(lambda d: d["body"]["sections"][0].update(lines=["solo"])),
            "rhyme",
            "debe tener entre 8 y 60",
        ),
        (
            mutate(lambda d: d["body"]["sections"].extend(d["body"]["sections"] * 8)),
            "rhyme",
            "debe tener entre 8 y 60",
        ),
        (
            mutate(lambda d: d["body"]["shots"][0].update(section_index=9)),
            "rhyme",
            "no existe",
        ),
        (
            mutate(lambda d: d["characters"].append(dict(d["characters"][0]))),
            "rhyme",
            "mismo id",
        ),
        (
            mutate(lambda d: d["body"]["scenes"].pop(), long_data),
            "long",
            "debe tener entre 4 y 10",
        ),
        (
            mutate(lambda d: d["body"]["scenes"][1].update(id="escena-1"), long_data),
            "long",
            "mismo id",
        ),
        (
            mutate(
                lambda d: d["body"]["scenes"][0]["beats"][0].update(speaker="nadie"),
                long_data,
            ),
            "long",
            "no existen",
        ),
        (
            mutate(lambda d: d["body"]["scenes"][0].update(beats=[]), long_data),
            "long",
            "beats",
        ),
    ],
)
def test_invalid_scripts_are_rejected_with_a_clear_message(data, fmt, message):
    with pytest.raises(EvergreenError, match=message):
        parse(data, fmt)


@pytest.mark.parametrize(("fmt", "language"), [("long", ES), ("rhyme", Language.en)])
def test_format_or_language_mismatch_is_rejected(fmt, language):
    with pytest.raises(EvergreenError, match="pero el video es"):
        parse(rhyme_data(), fmt, language)


def test_fenced_and_bom_responses_are_cleaned():
    body = json.dumps(rhyme_data(), ensure_ascii=False)
    for text in (f"```json\n{body}\n```", f"﻿{body}", f"```\n{body}```\n"):
        assert parse_script(text, "rhyme", ES).title == "Los patitos"
    assert clean_json("  {}  ") == "{}"


def test_non_json_gives_position_and_reason():
    with pytest.raises(
        EvergreenError, match=r"no es JSON válido \(línea 1, columna 1\)"
    ):
        parse_script("Claro, aquí tienes tu guion", "rhyme", ES)


def test_non_object_json_is_rejected():
    with pytest.raises(EvergreenError, match="no cumple el formato"):
        parse_script("[1, 2]", "rhyme", ES)


def test_markdown_does_not_double_the_final_period():
    from evergreen.script_writer.render import render_markdown

    data = rhyme_data()
    data["characters"][0]["visual"] = "Patito amarillo."
    data["characters"][0]["voice"] = "Aguda."
    md = render_markdown(parse(data))
    assert ".." not in md and "Patito amarillo. Voz: Aguda." in md


def test_old_scripts_without_shots_still_validate():
    data = long_data()
    for scene in data["body"]["scenes"]:
        del scene["shots"]
    for shot in rhyme_data()["body"]["shots"]:
        shot.pop("motion", None)
    assert parse(data, "long").body.scenes[0].shots == []
    old_rhyme = rhyme_data()
    for shot in old_rhyme["body"]["shots"]:
        del shot["motion"]
    assert parse(old_rhyme).body.shots[0].motion is None


@pytest.mark.parametrize(
    "shots",
    [
        [{"beat_index": 1, "description": "x"}],  # no empieza en 0
        [{"beat_index": 0, "description": "x"}, {"beat_index": 0, "description": "y"}],
        [{"beat_index": 1, "description": "x"}, {"beat_index": 0, "description": "y"}],
        [{"beat_index": 0, "description": "x"}, {"beat_index": 9, "description": "y"}],
    ],
)
def test_invalid_scene_shots_are_rejected(shots):
    data = mutate(lambda d: d["body"]["scenes"][0].update(shots=shots), long_data)
    with pytest.raises(EvergreenError, match="deben empezar en el diálogo 0"):
        parse(data, "long")


def test_markdown_lists_shots_with_motion():
    from evergreen.script_writer.render import render_markdown

    long_md = render_markdown(parse(long_data(), "long"))
    assert "Tomas:" in long_md and "movimiento: zoom lento" in long_md
    assert "movimiento: zoom lento hacia Lola" in render_markdown(parse(rhyme_data()))
