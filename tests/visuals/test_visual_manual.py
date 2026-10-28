import json

from script_samples import long_data, rhyme_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.visuals import register
from evergreen.visuals.manual import ImageManualAdapter


def video(tmp_path, fmt, data, aspect=None, stage_done=("script",)):
    v = project.create(
        "Los patitos", mf.Format(fmt), mf.Language.es, tmp_path, aspect=aspect
    )
    m = mf.load(v / "manifest.yaml")
    m.review_gates = []
    for name in stage_done:
        m.stages[name].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    d = v / "stages/script"
    d.mkdir(parents=True, exist_ok=True)
    if data:
        (d / "script.json").write_text(json.dumps(data), encoding="utf-8")
    return v


def run(v, stage):
    return runner.run(v, {stage: ImageManualAdapter()}).stages[stage]


def test_scenes_stage_lists_prompts_and_accepts_images_and_clips(tmp_path):
    v = video(
        tmp_path,
        "long",
        long_data(),
        stage_done=("script", "voice", "music", "characters"),
    )
    state = run(v, "scenes")
    assert state.status == mf.Status.awaiting_manual
    text = (v / "stages/scenes/MANUAL.md").read_text("utf-8")
    assert (
        "proporción 16:9" in text
        and "### escena-1-1 ★" in text
        and "### escena-1-2\n" in text
    )
    assert "Movimiento (Flow): zoom lento" in text and "Evitar:" in text

    inbox = v / "stages/scenes/inbox"
    for n in range(1, 5):
        for k in (1, 2):
            (inbox / f"escena-{n}-{k}.png").write_bytes(b"png")
    (inbox / "escena-1-1.mp4").write_bytes(b"clip")
    state = run(v, "scenes")
    assert state.status == mf.Status.done
    entries = json.loads((v / "stages/scenes/images.json").read_text("utf-8"))
    assert len(entries) == 8
    assert entries[0]["clip"] == "inbox/escena-1-1.mp4" and entries[1]["clip"] is None
    assert entries[0]["aspect"] == "16:9"
    assert "stages/scenes/inbox/escena-1-1.mp4" in state.outputs
    assert not (v / "stages/scenes/MANUAL.md").exists()


def test_rhyme_defaults_to_vertical_and_empty_image_is_reported(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data(), stage_done=("script", "song"))
    assert run(v, "visuals").status == mf.Status.awaiting_manual
    assert "proporción 9:16" in (v / "stages/visuals/MANUAL.md").read_text("utf-8")
    (v / "stages/visuals/inbox/toma-1.jpg").write_bytes(b"")
    run(v, "visuals")
    assert "vacío" in (v / "stages/visuals/MANUAL.md").read_text("utf-8")
    (v / "stages/visuals/inbox/toma-1.jpg").write_bytes(b"jpg")
    assert run(v, "visuals").status == mf.Status.done


def test_empty_clip_is_ignored(tmp_path):
    v = video(
        tmp_path, "rhyme", rhyme_data(), aspect="16:9", stage_done=("script", "song")
    )
    inbox = v / "stages/visuals/inbox"
    inbox.mkdir(parents=True)
    (inbox / "toma-1.png").write_bytes(b"x")
    (inbox / "toma-1.mp4").write_bytes(b"")
    run(v, "visuals")
    entries = json.loads((v / "stages/visuals/images.json").read_text("utf-8"))
    assert entries[0]["clip"] is None and entries[0]["aspect"] == "16:9"


def test_missing_script_and_wrong_format_fail_clearly(tmp_path):
    v = video(tmp_path, "rhyme", None, stage_done=("script", "song"))
    assert "etapa `script`" in run(v, "visuals").error
    w = video(
        tmp_path / "otro", "long", long_data(), stage_done=("script", "voice", "music")
    )
    (w / "stages/characters").mkdir(exist_ok=True)
    state = runner.run(w, {"characters": ImageManualAdapter()}).stages["characters"]
    assert state.status == mf.Status.awaiting_manual  # long + characters sí aplica
    x = video(tmp_path / "otro2", "rhyme", rhyme_data(), stage_done=("script", "song"))
    state = runner.run(x, {"visuals": ImageManualAdapter()}).stages["visuals"]
    assert state.status == mf.Status.awaiting_manual


def test_register_adds_the_three_stages():
    from evergreen import registry

    register()
    assert {"visuals", "characters", "scenes"} <= set(registry.ADAPTERS)


def test_stage_that_does_not_match_the_script_format_is_an_error(tmp_path):
    import pytest

    from evergreen.adapters.base import StageContext
    from evergreen.errors import EvergreenError

    v = video(tmp_path, "rhyme", rhyme_data())
    ctx = StageContext("scenes", v / "stages/script", v, mf.load(v / "manifest.yaml"))
    with pytest.raises(EvergreenError, match="no aplica"):
        ImageManualAdapter().run(ctx)
