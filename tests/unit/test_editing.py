import json

import pytest
from script_samples import long_data

from evergreen import editing, project
from evergreen import manifest as mf
from evergreen.errors import EvergreenError


def long_video(tmp_path):
    v = project.create(
        "Los patitos", mf.Format.long, mf.Language.es, tmp_path, brief="tema"
    )
    m = mf.load(v / "manifest.yaml")
    for st in m.stages.values():
        st.status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    (v / "stages/script/script.json").write_text(
        json.dumps(long_data()), encoding="utf-8"
    )
    return v


def stale(v):
    return sorted(n for n, s in mf.load(v / "manifest.yaml").stages.items() if s.stale)


def test_script_edit_is_saved_rendered_and_marks_dependents(tmp_path):
    v = long_video(tmp_path)
    data = long_data()
    data["title"] = "Título nuevo"
    assert editing.save_script(v, json.dumps(data)) == [
        "voice",
        "music",
        "characters",
        "scenes",
        "assembly",
    ]
    assert (
        json.loads((v / "stages/script/script.json").read_text())["title"]
        == "Título nuevo"
    )
    assert "Título nuevo" in (v / "stages/script/script.md").read_text()
    assert stale(v) == ["assembly", "characters", "music", "scenes", "voice"]


def test_invalid_script_changes_nothing(tmp_path):
    v = long_video(tmp_path)
    before = (v / "stages/script/script.json").read_text()
    data = long_data()
    data["body"]["scenes"][0]["shots"][0]["beat_index"] = 5
    for bad in ("{no json", json.dumps(data)):
        with pytest.raises(EvergreenError):
            editing.save_script(v, bad)
    assert (v / "stages/script/script.json").read_text() == before and stale(v) == []


def test_script_must_exist_and_cast_is_enforced(tmp_path):
    v = long_video(tmp_path)
    (v / "stages/script/script.json").unlink()
    with pytest.raises(EvergreenError, match="Aún no hay guion"):
        editing.save_script(v, "{}")
    v = long_video(tmp_path / "otro")
    (tmp_path / "otro/cast.yaml").write_text(
        "characters:\n  - id: solo\n    name: Solo\n    visual: x\n    voice: y\n",
        encoding="utf-8",
    )
    with pytest.raises(EvergreenError, match="no están en cast.yaml"):
        editing.save_script(v, json.dumps(long_data()))


def test_title_only_change_does_not_stale_but_brief_change_does(tmp_path):
    v = long_video(tmp_path)
    assert editing.set_title_and_brief(v, "Otro título", "tema") == []
    assert mf.load(v / "manifest.yaml").title == "Otro título"
    assert editing.set_title_and_brief(v, "Otro título", "tema nuevo")[0] == "script"
    for title, brief, msg in (("  ", None, "vacío"), ("t", "x" * 501, "500")):
        with pytest.raises(EvergreenError, match=msg):
            editing.set_title_and_brief(v, title, brief)


def test_config_edit_validates_then_marks_only_affected_videos(tmp_path):
    v = long_video(tmp_path)
    r = project.create("Rima", mf.Format.rhyme, mf.Language.es, tmp_path)
    m = mf.load(r / "manifest.yaml")
    m.stages["visuals"].status = mf.Status.done
    mf.save(m, r / "manifest.yaml")
    assert editing.save_config(tmp_path, "style", "style: acuarela suave\n") == {
        v.name: ["characters", "scenes"],
        r.name: ["visuals"],
    }
    assert (tmp_path / "style.yaml").read_text() == "style: acuarela suave\n"
    assert editing.save_config(tmp_path, "voices", "narrator: Charon\n") == {
        v.name: ["voice"]
    }


def test_invalid_config_is_not_written(tmp_path):
    with pytest.raises(EvergreenError, match="cast.yaml"):
        editing.save_config(tmp_path, "cast", "characters: []\n")
    assert not (tmp_path / "cast.yaml").exists()
    with pytest.raises(EvergreenError, match="No sé editar"):
        editing.save_config(tmp_path, "otro", "")
