import json

import pytest
from script_samples import long_data, rhyme_data

from evergreen.errors import EvergreenError
from evergreen.manifest import Language
from evergreen.script_writer.models import parse_script
from evergreen.visuals.prompts import plan_images
from evergreen.visuals.style import DEFAULT_STYLE, Style, load_style

STYLE = Style(style="acuarela suave", negative="texto")


def script(data, fmt):
    return parse_script(json.dumps(data), fmt, Language.es)


def test_style_default_file_and_invalid(tmp_path):
    assert load_style(tmp_path).style == DEFAULT_STYLE
    (tmp_path / "style.yaml").write_text("style: acuarela\n", encoding="utf-8")
    assert load_style(tmp_path).style == "acuarela"
    (tmp_path / "style.yaml").write_text("style: ''\n", encoding="utf-8")
    with pytest.raises(EvergreenError, match="style.yaml"):
        load_style(tmp_path)


def test_character_sheets_use_the_exact_description():
    reqs = plan_images("characters", script(long_data(), "long"), STYLE)
    assert [r.key for r in reqs] == ["personaje-lola", "personaje-pipo"]
    assert "Lola: patita amarilla con botas rojas." in reqs[0].prompt
    assert reqs[0].prompt.startswith("acuarela suave.") and reqs[0].negative == "texto"


def test_scene_shots_include_only_the_characters_that_speak_in_them():
    data = long_data()
    scene = data["body"]["scenes"][0]
    scene["beats"] = [
        {"speaker": "lola", "text": "a", "emotion": "e"},
        {"speaker": "pipo", "text": "b", "emotion": "e"},
        {"speaker": "narrator", "text": "c", "emotion": "e"},
    ]
    scene["shots"] = [
        {"beat_index": 0, "description": "primera", "motion": "zoom"},
        {"beat_index": 1, "description": "segunda"},
    ]
    reqs = plan_images("scenes", script(data, "long"), STYLE)
    first, second = reqs[0], reqs[1]
    assert (first.key, second.key) == ("escena-1-1", "escena-1-2")
    assert "Lola:" in first.prompt and "Pipo:" not in first.prompt
    assert "Pipo:" in second.prompt and "Lola:" not in second.prompt
    assert first.motion == "zoom" and second.motion is None
    assert first.priority and not second.priority


def test_scene_without_shots_falls_back_to_visual_notes():
    data = long_data()
    for s in data["body"]["scenes"]:
        del s["shots"]
    reqs = plan_images("scenes", script(data, "long"), STYLE)
    assert (
        len(reqs) == 4 and "luz de mañana" in reqs[0].prompt and reqs[0].motion is None
    )


def test_rhyme_shots_and_priority_per_section():
    data = rhyme_data()
    data["body"]["shots"] = [
        {
            "section_index": 0,
            "description": "uno",
            "characters": ["lola"],
            "motion": "m",
        },
        {"section_index": 0, "description": "dos", "characters": []},
        {"section_index": 1, "description": "tres", "characters": ["pipo"]},
    ]
    reqs = plan_images("visuals", script(data, "rhyme"), STYLE)
    assert [r.key for r in reqs] == ["toma-1", "toma-2", "toma-3"]
    assert [r.priority for r in reqs] == [True, False, True]
    assert "Lola:" in reqs[0].prompt and reqs[0].motion == "m"


def test_stage_that_does_not_apply_is_rejected():
    with pytest.raises(ValueError, match="no aplica"):
        plan_images("visuals", script(long_data(), "long"), STYLE)
    with pytest.raises(ValueError, match="no aplica"):
        plan_images("nada", script(long_data(), "long"), STYLE)
