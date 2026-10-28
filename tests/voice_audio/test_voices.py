import pytest

from evergreen.errors import EvergreenError
from evergreen.voice_audio.voices import (
    DEFAULT_NARRATOR,
    POOL,
    Voices,
    assign,
    load_voices,
)


def test_no_file_gives_defaults(tmp_path):
    assert load_voices(tmp_path) == Voices()


def test_file_overrides_and_empty_file_is_ok(tmp_path):
    (tmp_path / "voices.yaml").write_text(
        "narrator: Zephyr\ncharacters: {lola: Puck}\n", encoding="utf-8"
    )
    v = load_voices(tmp_path)
    assert v.narrator == "Zephyr" and v.characters == {"lola": "Puck"}
    (tmp_path / "voices.yaml").write_text("", encoding="utf-8")
    assert load_voices(tmp_path).narrator == DEFAULT_NARRATOR


@pytest.mark.parametrize("text", ["narrator: ''", "extra: 1", "- x", ":\n -"])
def test_invalid_file_is_rejected(tmp_path, text):
    (tmp_path / "voices.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(EvergreenError, match="voices.yaml"):
        load_voices(tmp_path)


def test_default_voices_are_stable_distinct_and_explicit_ones_win():
    ids = ["lola", "pipo", "tito", "nina"]
    first = assign(ids, Voices())
    assert first == assign(list(reversed(ids)), Voices())  # no depende del orden
    chosen = [first[i] for i in ids]
    assert len(set(chosen)) == 4 and first["narrator"] not in chosen
    assert all(v in POOL for v in chosen)
    explicit = assign(ids, Voices(characters={"lola": "Orus"}))
    assert explicit["lola"] == "Orus" and "Orus" not in [explicit[i] for i in ids[1:]]


def test_pool_exhausted_falls_back_without_crashing():
    ids = [f"p{n}" for n in range(len(POOL) + 2)]
    assert len(assign(ids, Voices())) == len(ids) + 1
