from typer.testing import CliRunner

from evergreen import manifest as mf
from evergreen import project, registry
from evergreen.cli import app

runner = CliRunner()


def test_full_video_in_manual_mode_reaches_done(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(registry, "ADAPTERS", {})  # nada automatizado
    video = project.create("Patitos", mf.Format.rhyme, mf.Language.es, tmp_path)

    for stage in registry.STAGES["rhyme"]:
        result = runner.invoke(app, ["run", video.name])
        assert result.exit_code == 0
        stage_dir = video / "stages" / stage
        assert f"`{registry.MANUAL_FILES[stage][0]}`" in (
            stage_dir / "MANUAL.md"
        ).read_text(encoding="utf-8")
        for f in registry.MANUAL_FILES[stage]:
            (stage_dir / "inbox" / f).write_text("x", encoding="utf-8")
        if stage in mf.load(video / "manifest.yaml").review_gates:
            runner.invoke(
                app, ["run", video.name]
            )  # completa la etapa y se detiene en la puerta
            assert runner.invoke(app, ["approve", video.name, stage]).exit_code == 0

    assert runner.invoke(app, ["run", video.name]).exit_code == 0
    stages = mf.load(video / "manifest.yaml").stages
    assert all(s.status == mf.Status.done for s in stages.values())
