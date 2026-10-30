import pytest
from typer.testing import CliRunner

from evergreen import manifest as mf
from evergreen import project, reopen
from evergreen.cli import app
from evergreen.errors import EvergreenError


def video(tmp_path, fmt="long"):
    v = project.create("Los patitos", mf.Format(fmt), mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    for st in m.stages.values():
        st.status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    return v


def states(v):
    return mf.load(v / "manifest.yaml").stages


def test_reopen_archives_files_and_marks_dependents_stale(tmp_path):
    v = video(tmp_path)
    d = v / "stages/voice"
    (d / "inbox").mkdir()
    (d / "inbox/voice.mp3").write_text("x")
    (d / "timeline.json").write_text("[]")
    (d / "work").mkdir()
    (d / "work/cache").write_text("c")
    assert reopen.reopen(v, "voice") == ["assembly"]
    s = states(v)
    assert (
        s["voice"].status == mf.Status.pending
        and s["voice"].outputs == []
        and not s["voice"].stale
    )
    assert s["assembly"].stale and not s["music"].stale
    assert not (d / "timeline.json").exists() and (d / "work/cache").exists()
    (archived,) = (d / "archive").iterdir()
    assert (archived / "inbox/voice.mp3").read_text() == "x" and (
        archived / "timeline.json"
    ).exists()


def test_reopening_the_script_stales_everything_else(tmp_path):
    v = video(tmp_path)
    assert reopen.reopen(v, "script") == [
        "voice",
        "music",
        "characters",
        "scenes",
        "assembly",
    ]
    assert not (v / "stages/script/archive").exists()  # sin archivos, nada que archivar


def test_rhyme_dependencies_and_unfinished_stages_are_not_marked(tmp_path):
    v = video(tmp_path, "rhyme")
    m = mf.load(v / "manifest.yaml")
    m.stages["visuals"].status = mf.Status.pending
    mf.save(m, v / "manifest.yaml")
    assert reopen.reopen(v, "script") == ["song", "assembly"]


def test_errors_unknown_and_running(tmp_path):
    v = video(tmp_path)
    with pytest.raises(EvergreenError, match="no tiene la etapa"):
        reopen.reopen(v, "nada")
    m = mf.load(v / "manifest.yaml")
    m.stages["voice"].status = mf.Status.running
    mf.save(m, v / "manifest.yaml")
    with pytest.raises(EvergreenError, match="se está ejecutando"):
        reopen.reopen(v, "voice")


def test_keep_clears_stale_and_archive_never_overwrites(tmp_path):
    v = video(tmp_path)
    reopen.reopen(v, "voice")
    reopen.keep(v, "assembly")
    assert not states(v)["assembly"].stale
    d = tmp_path / "s"
    d.mkdir()
    for _ in range(2):
        (d / "a.txt").write_text("1")
        reopen.archive_files(d, [d / "a.txt"])
    assert len(list((d / "archive").iterdir())) == 2
    assert reopen.archive_files(d, [d / "no-existe"]) is None


def test_old_manifest_without_stale_still_loads(tmp_path):
    v = video(tmp_path)
    text = (v / "manifest.yaml").read_text().replace("    stale: false\n", "")
    (v / "manifest.yaml").write_text(text)
    assert not states(v)["voice"].stale


def test_cli_reopen_and_status(tmp_path, monkeypatch):
    v = video(tmp_path)
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    r = CliRunner().invoke(app, ["reopen", v.name, "voice"])
    assert (
        r.exit_code == 0
        and "Reabierta: voice" in r.output
        and "Desactualizadas: assembly" in r.output
    )
    assert "(desactualizada)" in CliRunner().invoke(app, ["status", v.name]).output
    assert CliRunner().invoke(app, ["reopen", v.name, "nada"]).exit_code == 1


def test_regenerate_item_archives_only_that_item(tmp_path):
    v = video(tmp_path)
    d = v / "stages/scenes"
    (d / "inbox").mkdir()
    for name in (
        "escena-1-1.jpg",
        "escena-1-2.jpg",
        "inbox/escena-1-1.mp4",
        "images.json",
    ):
        (d / name).write_text("x")
    assert reopen.regenerate_item(v, "scenes", "escena-1-1") == ["assembly"]
    assert (
        not (d / "escena-1-1.jpg").exists()
        and not (d / "inbox/escena-1-1.mp4").exists()
    )
    assert (d / "escena-1-2.jpg").exists() and (d / "images.json").exists()
    assert states(v)["scenes"].status == mf.Status.pending
    (archived,) = (d / "archive").iterdir()
    assert (archived / "inbox/escena-1-1.mp4").exists()


def test_regenerate_items_archives_several_and_leaves_the_rest(tmp_path):
    v = video(tmp_path)
    d = v / "stages/voice"
    for k in ("escena-1", "escena-2", "escena-3"):
        (d / f"{k}.wav").write_text("x")
    assert reopen.regenerate_items(
        v, "voice", ["escena-1", "escena-3", "escena-1"]
    ) == ["assembly"]
    assert [p.name for p in d.glob("*.wav")] == ["escena-2.wav"]
    (archived,) = (
        d / "archive"
    ).iterdir()  # un solo archivo de respaldo para todo el lote
    assert sorted(p.name for p in archived.iterdir()) == [
        "escena-1.wav",
        "escena-3.wav",
    ]
    assert states(v)["voice"].status == mf.Status.pending


def test_regenerate_items_is_all_or_nothing(tmp_path):
    v = video(tmp_path)
    d = v / "stages/voice"
    (d / "escena-1.wav").write_text("x")
    with pytest.raises(EvergreenError, match="No encuentro 'escena-9'"):
        reopen.regenerate_items(v, "voice", ["escena-1", "escena-9"])
    with pytest.raises(EvergreenError, match="al menos un elemento"):
        reopen.regenerate_items(v, "voice", [])
    assert (d / "escena-1.wav").exists() and not (d / "archive").exists()
    assert states(v)["voice"].status == mf.Status.done


@pytest.mark.parametrize("key", ["nada", "../manifest", "escena-1-"])
def test_regenerate_item_rejects_unknown_or_unsafe_keys(tmp_path, key):
    v = video(tmp_path)
    (v / "stages/voice/escena-1.wav").write_text("x")
    with pytest.raises(EvergreenError, match="No encuentro"):
        reopen.regenerate_item(v, "voice", key)
    assert states(v)["voice"].status == mf.Status.done


def test_regenerate_item_refuses_running_stage(tmp_path):
    v = video(tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.stages["voice"].status = mf.Status.running
    mf.save(m, v / "manifest.yaml")
    with pytest.raises(EvergreenError, match="se está ejecutando"):
        reopen.regenerate_item(v, "voice", "escena-1")
