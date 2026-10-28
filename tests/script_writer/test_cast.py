import json

import pytest
from gemini_fakes import FakeSDK
from script_samples import rhyme_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.errors import EvergreenError
from evergreen.script_writer.adapter import ScriptAdapter
from evergreen.script_writer.cast import apply_cast, load_cast
from evergreen.script_writer.gemini import GeminiClient
from evergreen.script_writer.models import parse_script

CAST = """characters:
  - {id: lola, name: Lola Fija, visual: patita fija, voice: voz fija}
  - {id: pipo, name: Pipo Fijo, visual: pato fijo, voice: otra voz}
"""


def video(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    v = project.create("Los patitos", mf.Format.rhyme, mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.review_gates = []
    mf.save(m, v / "manifest.yaml")
    return v


def test_no_cast_file_means_no_cast(tmp_path):
    assert load_cast(tmp_path) is None


@pytest.mark.parametrize(
    "text",
    ["characters: []", "- x", "characters: [{id: a}]", CAST + CAST[16:], ":\n -"],
)
def test_invalid_cast_is_rejected(tmp_path, text):
    (tmp_path / "cast.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(EvergreenError, match="cast.yaml"):
        load_cast(tmp_path)


def test_cast_overrides_what_the_model_wrote_and_rejects_strangers(tmp_path):
    (tmp_path / "cast.yaml").write_text(CAST, encoding="utf-8")
    cast = load_cast(tmp_path)
    script = parse_script(json.dumps(rhyme_data()), "rhyme", mf.Language.es)
    fixed = apply_cast(script, cast)
    assert [c.name for c in fixed.characters] == ["Lola Fija", "Pipo Fijo"]
    stranger = script.model_copy(
        update={"characters": [script.characters[0].model_copy(update={"id": "otro"})]}
    )
    with pytest.raises(EvergreenError, match="otro"):
        apply_cast(stranger, cast)


def test_api_prompt_lists_the_cast_and_result_uses_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    (tmp_path / "cast.yaml").write_text(CAST, encoding="utf-8")
    v = video(tmp_path, monkeypatch)
    sdk = FakeSDK(json.dumps(rhyme_data()))
    adapter = ScriptAdapter(
        lambda k, m: GeminiClient(k, m, sdk=sdk, sleep=lambda s: None)
    )
    runner.run(v, {"script": adapter})
    assert "`lola`: Lola Fija" in sdk.models.requests[0]["contents"]
    saved = json.loads((v / "stages/script/script.json").read_text("utf-8"))
    assert saved["characters"][0]["name"] == "Lola Fija"


def test_manual_mode_reports_unknown_characters_in_manual_md(tmp_path, monkeypatch):
    (tmp_path / "cast.yaml").write_text(CAST.replace("pipo", "otro"), encoding="utf-8")
    v = video(tmp_path, monkeypatch)
    inbox = v / "stages/script/inbox"
    inbox.mkdir(parents=True)
    (inbox / "script.json").write_text(json.dumps(rhyme_data()), encoding="utf-8")
    state = runner.run(v, {"script": ScriptAdapter()}).stages["script"]
    assert state.status == mf.Status.awaiting_manual
    assert "pipo" in (v / "stages/script/MANUAL.md").read_text("utf-8")
