import json

import pytest
from script_samples import long_data, rhyme_data

from evergreen.manifest import Language
from evergreen.script_writer.models import RhymeScript, Variation, parse_script
from evergreen.script_writer.variation import (
    AXES,
    TONES,
    existing_scripts,
    find_similar,
    pick_variation,
    similarity,
)


def rhyme(verse_lines, chorus_lines, chorus_times=1, lang="es"):
    data = rhyme_data(lang)
    verse = {"kind": "verse", "lines": verse_lines}
    chorus = {"kind": "chorus", "lines": chorus_lines}
    data["body"]["sections"] = [verse] + [chorus] * chorus_times + [verse]
    return RhymeScript.model_validate(data)


A = [
    "el patito nada feliz",
    "en el estanque azul",
    "mueve sus patitas",
    "y sale a pasear",
]
B = [
    "la luna sube despacio",
    "sobre el viejo tejado",
    "los grillos cantan bajito",
    "y todo está en calma",
]
CHORUS = ["cuac cuac cuac", "todos a cantar", "cuac cuac cuac", "vamos a bailar"]


def test_same_seed_same_variation():
    assert pick_variation("rhyme", seed=7) == pick_variation("rhyme", seed=7)


def test_twenty_seeds_give_at_least_five_combinations():
    combos = {
        (v.structure, v.tone)
        for v in (pick_variation("rhyme", seed=s) for s in range(20))
    }
    assert len(combos) >= 5


def test_avoids_used_combinations_while_free_ones_remain():
    first = AXES["rhyme"]["structures"][0]
    used = [Variation(seed=0, structure=first, tone=t, twist="x") for t in TONES]
    for seed in range(30):
        assert pick_variation("rhyme", seed=seed, avoid=used).structure != first


def test_when_every_combination_is_used_it_still_returns_one():
    every = [
        Variation(seed=0, structure=s, tone=t, twist="x")
        for s in AXES["rhyme"]["structures"]
        for t in TONES
    ]
    picked = pick_variation("rhyme", seed=1, avoid=every)
    assert picked.structure in AXES["rhyme"]["structures"]


def test_identical_scripts_score_one_and_unrelated_score_near_zero():
    assert similarity(rhyme(A, CHORUS), rhyme(A, CHORUS)) == 1.0
    assert similarity(rhyme(A, CHORUS), rhyme(B, ["la la la la"] * 4)) < 0.05


def test_repeated_chorus_does_not_inflate_similarity():
    once = similarity(rhyme(A, CHORUS), rhyme(B, CHORUS, 1))
    five_times = similarity(rhyme(A, CHORUS, 5), rhyme(B, CHORUS, 5))
    assert five_times == pytest.approx(once)
    assert five_times < 0.35


def test_find_similar_names_the_video_or_returns_none():
    new = rhyme(A, CHORUS)
    others = [("video-b", rhyme(B, CHORUS)), ("video-a", rhyme(A, CHORUS))]
    assert find_similar(new, others) == ("video-a", 1.0)
    assert find_similar(new, [("video-b", rhyme(B, ["la la la la"] * 4))]) is None
    assert find_similar(new, []) is None
    assert find_similar(new, others, threshold=1.1) is None


def test_long_scripts_are_compared_by_dialogue():
    a = parse_script(json.dumps(long_data(), ensure_ascii=False), "long", Language.es)
    assert similarity(a, a) == 1.0


def save(root, name, data):
    path = root / name / "stages" / "script"
    path.mkdir(parents=True)
    (path / "script.json").write_text(json.dumps(data), encoding="utf-8")


def test_existing_scripts_skips_unreadable_and_excluded(tmp_path):
    save(tmp_path, "uno", rhyme_data())
    save(tmp_path, "dos", rhyme_data())
    (tmp_path / "roto" / "stages" / "script").mkdir(parents=True)
    (tmp_path / "roto" / "stages" / "script" / "script.json").write_text(
        "{no", encoding="utf-8"
    )
    save(tmp_path, "viejo", {"format": "rhyme"})  # no cumple el contrato
    assert [v for v, _ in existing_scripts(tmp_path)] == ["dos", "uno"]
    assert [v for v, _ in existing_scripts(tmp_path, exclude="uno")] == ["dos"]
    assert existing_scripts(tmp_path / "no-existe") == []


def test_each_format_draws_only_from_its_own_axes():
    for fmt in ("rhyme", "long"):
        for seed in range(40):
            v = pick_variation(fmt, seed=seed)
            assert v.structure in AXES[fmt]["structures"]
            assert v.twist in AXES[fmt]["twists"]


def test_long_axes_do_not_talk_about_songs():
    text = " ".join(AXES["long"]["structures"] + AXES["long"]["twists"])
    assert not any(
        word in text for word in ("estrofa", "estribillo", "verso", "canción")
    )


def test_long_format_still_gives_varied_combinations():
    combos = {
        (v.structure, v.tone)
        for v in (pick_variation("long", seed=s) for s in range(20))
    }
    assert len(combos) >= 5
