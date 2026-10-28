import json

import pytest
from script_samples import long_data, rhyme_data
from typer.testing import CliRunner

from evergreen import manifest as mf
from evergreen import project
from evergreen.cli import app
from evergreen.script_writer import adapter as adapter_module
from evergreen.script_writer.models import Variation

runner = CliRunner()
CHOSEN = Variation(
    seed=99, structure="cuenta regresiva", tone="curioso", twist="un eco"
)
SAMPLES = {"rhyme": rhyme_data, "long": long_data}


@pytest.fixture(autouse=True)
def fixed_variation(monkeypatch):
    monkeypatch.setattr(adapter_module, "pick_variation", lambda fmt, avoid=(): CHOSEN)


def make_video(
    tmp_path, monkeypatch, fmt="rhyme", language="es", brief="patitos que nadan"
):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    video = project.create(
        "Los patitos", mf.Format(fmt), mf.Language(language), tmp_path, brief
    )
    m = mf.load(video / "manifest.yaml")
    m.review_gates = []  # sin pausas: estas pruebas miran solo la etapa `script`
    mf.save(m, video / "manifest.yaml")
    return video


def stage(video):
    return mf.load(video / "manifest.yaml").stages["script"]


def inbox(video):
    return video / "stages" / "script" / "inbox"


def test_without_a_response_it_waits_with_the_full_prompt(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch)
    result = runner.invoke(app, ["run", video.name])
    assert result.exit_code == 0
    assert stage(video).status == mf.Status.awaiting_manual
    text = (video / "stages" / "script" / "MANUAL.md").read_text(encoding="utf-8")
    for expected in (
        "patitos que nadan",
        "cuenta regresiva",
        "Todos los archivos",
        f"evergreen run {video.name}",
        '"style_prompt"',
    ):
        assert expected in text


@pytest.mark.parametrize(
    ("fmt", "language"), [(f, lang) for f in SAMPLES for lang in ("es", "en")]
)
def test_a_valid_response_finishes_the_stage_in_all_four_cases(
    tmp_path, monkeypatch, fmt, language
):
    video = make_video(tmp_path, monkeypatch, fmt, language)
    runner.invoke(app, ["run", video.name])
    (inbox(video) / "script.json").write_text(
        json.dumps(SAMPLES[fmt](language), ensure_ascii=False), encoding="utf-8"
    )
    runner.invoke(app, ["run", video.name])

    state = stage(video)
    assert state.status == mf.Status.done
    assert state.outputs == ["stages/script/script.json", "stages/script/script.md"]
    saved = json.loads(
        (video / "stages/script/script.json").read_text(encoding="utf-8")
    )
    assert saved["format"] == fmt and saved["language"] == language
    assert saved["variation"] == CHOSEN.model_dump()  # la elegida, no la del chat
    assert not (video / "stages/script/MANUAL.md").exists()


def respond(video, raw: bytes, name="script.json"):
    (inbox(video) / name).write_bytes(raw)
    runner.invoke(app, ["run", video.name])


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        (b"```json\n" + json.dumps(rhyme_data()).encode() + b"\n```", "script.json"),
        (json.dumps(rhyme_data()).encode(), "script.json.txt"),
        (json.dumps(rhyme_data(), ensure_ascii=False).encode("utf-16"), "script.json"),
        (b"\xef\xbb\xbf" + json.dumps(rhyme_data()).encode(), "script.json"),
    ],
)
def test_fences_txt_extension_utf16_and_bom_are_accepted(
    tmp_path, monkeypatch, raw, name
):
    video = make_video(tmp_path, monkeypatch)
    runner.invoke(app, ["run", video.name])
    respond(video, raw, name)
    assert stage(video).status == mf.Status.done


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"Claro, aqui tienes el guion", "no es JSON válido"),
        (
            json.dumps({**rhyme_data(), "format": "long"}).encode(),
            "no cumple el formato",
        ),
        (b'{"t": "caf\xe9"}', "UTF-8"),
    ],
)
def test_an_invalid_file_keeps_waiting_and_explains_why(
    tmp_path, monkeypatch, raw, expected
):
    video = make_video(tmp_path, monkeypatch)
    runner.invoke(app, ["run", video.name])
    respond(video, raw)
    assert stage(video).status == mf.Status.awaiting_manual
    manual = (video / "stages/script/MANUAL.md").read_text(encoding="utf-8")
    assert "Problema con tu archivo" in manual and expected in manual

    respond(video, json.dumps(rhyme_data()).encode())  # el usuario lo corrige
    assert stage(video).status == mf.Status.done


def test_script_md_is_readable(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch)
    runner.invoke(app, ["run", video.name])
    respond(video, json.dumps(rhyme_data()).encode())
    text = (video / "stages/script/script.md").read_text(encoding="utf-8")
    for expected in (
        "# Los patitos",
        "## Personajes",
        "**Lola**",
        "### Verso 1",
        "### Estribillo 1",
        "## Tomas",
    ):
        assert expected in text


def test_long_script_md_shows_dialogue(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch, "long")
    runner.invoke(app, ["run", video.name])
    respond(video, json.dumps(long_data()).encode())
    text = (video / "stages/script/script.md").read_text(encoding="utf-8")
    assert (
        "## Escena 1" in text
        and "**Lola** (alegre): ¡Hola!" in text
        and "**Narrador**" in text
    )


def test_variation_is_stable_between_runs_while_waiting(tmp_path, monkeypatch):
    monkeypatch.undo()  # sin variación fija
    video = make_video(tmp_path, monkeypatch)
    runner.invoke(app, ["run", video.name])
    first = (video / "stages/script/variation.json").read_text(encoding="utf-8")
    runner.invoke(app, ["run", video.name])
    assert (video / "stages/script/variation.json").read_text(encoding="utf-8") == first


def test_api_key_never_reaches_manual_or_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-123")
    monkeypatch.setenv(
        "EVERGREEN_SCRIPT_MODE", "manual"
    )  # con clave, el modo por defecto sería API
    video = make_video(tmp_path, monkeypatch)
    out = runner.invoke(app, ["run", video.name]).output
    respond(video, json.dumps(rhyme_data()).encode())
    texts = [out] + [
        p.read_text(encoding="utf-8") for p in video.rglob("*") if p.is_file()
    ]
    assert not any("fake-key-123" in t for t in texts)


def test_corrupt_variation_file_is_replaced(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch)
    runner.invoke(app, ["run", video.name])
    (video / "stages/script/variation.json").write_text("{roto", encoding="utf-8")
    runner.invoke(app, ["run", video.name])
    assert Variation.model_validate_json(
        (video / "stages/script/variation.json").read_text("utf-8")
    )


def test_default_gate_then_next_stage_from_new_to_song(tmp_path, monkeypatch):
    """Flujo real del usuario: new -> run -> pegar guion -> run -> approve -> run."""
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    video = project.create("Los patitos", mf.Format.rhyme, mf.Language.es, tmp_path)
    runner.invoke(app, ["run", video.name])
    respond(video, json.dumps(rhyme_data()).encode())
    assert stage(video).status == mf.Status.awaiting_approval  # puerta por defecto

    assert runner.invoke(app, ["approve", video.name, "script"]).exit_code == 0
    runner.invoke(app, ["run", video.name])
    stages = mf.load(video / "manifest.yaml").stages
    assert stages["script"].status == mf.Status.done
    assert stages["song"].status == mf.Status.awaiting_manual
