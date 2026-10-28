import json

import pytest
from script_samples import long_data, rhyme_data

from evergreen.assembly.timing import long_spans, rhyme_spans, scene_seconds_from_total
from evergreen.manifest import Language
from evergreen.script_writer.models import parse_script


def long_script(mutate=None):
    data = long_data()
    if mutate:
        mutate(data)
    return parse_script(json.dumps(data), "long", Language.es)


def test_scene_time_is_split_between_shots_by_dialogue_length():
    def m(d):
        scene = d["body"]["scenes"][0]
        scene["beats"] = [
            {"speaker": "lola", "text": "a" * 30, "emotion": "e"},
            {"speaker": "pipo", "text": "b" * 10, "emotion": "e"},
        ]
        scene["shots"] = [
            {"beat_index": 0, "description": "x"},
            {"beat_index": 1, "description": "y"},
        ]

    spans = long_spans(long_script(m), {f"escena-{n}": 8.0 for n in range(1, 5)})
    first = [s for s in spans if s.scene_id == "escena-1"]
    assert [s.key for s in first] == ["escena-1-1", "escena-1-2"]
    assert [s.seconds for s in first] == pytest.approx([6.0, 2.0])


def test_every_scene_keeps_its_exact_duration_and_old_scripts_get_one_shot():
    def m(d):
        for s in d["body"]["scenes"]:
            del s["shots"]

    script = long_script(m)
    seconds = {f"escena-{n}": 3.0 + n for n in range(1, 5)}
    spans = long_spans(script, seconds)
    assert [s.key for s in spans] == [f"escena-{n}-1" for n in range(1, 5)]
    assert [s.seconds for s in spans] == pytest.approx(list(seconds.values()))
    with_shots = long_spans(long_script(), seconds)
    assert sum(s.seconds for s in with_shots) == pytest.approx(sum(seconds.values()))


def test_manual_voice_splits_the_total_by_scene_text():
    def m(d):
        d["body"]["scenes"][0]["beats"] = [
            {"speaker": "lola", "text": "x" * 100, "emotion": "e"}
        ]
        d["body"]["scenes"][0]["shots"] = [{"beat_index": 0, "description": "x"}]

    script = long_script(m)
    per_scene = scene_seconds_from_total(script, 60.0)
    assert sum(per_scene.values()) == pytest.approx(60.0)
    assert per_scene["escena-1"] > per_scene["escena-2"]


def rhyme_script(shots):
    data = rhyme_data()
    data["body"]["shots"] = shots
    return parse_script(json.dumps(data), "rhyme", Language.es)


def test_rhyme_total_is_the_song_length_and_sections_share_by_lines():
    # rhyme_data: sección 0 con 4 líneas, sección 1 con 4 líneas, sección 2 con 4 líneas
    shots = [
        {"section_index": 0, "description": "a", "characters": []},
        {"section_index": 0, "description": "b", "characters": []},
        {"section_index": 1, "description": "c", "characters": []},
    ]
    spans = rhyme_spans(rhyme_script(shots), 60.0)
    assert [s.key for s in spans] == ["toma-1", "toma-2", "toma-3"]
    assert sum(s.seconds for s in spans) == pytest.approx(60.0)
    assert (
        spans[0].seconds
        == pytest.approx(spans[1].seconds)
        == pytest.approx(spans[2].seconds / 2 * 1)
    )


def test_sections_without_shots_give_their_time_to_the_others():
    spans = rhyme_spans(
        rhyme_script([{"section_index": 1, "description": "c", "characters": []}]), 40.0
    )
    assert [s.seconds for s in spans] == pytest.approx([40.0])
