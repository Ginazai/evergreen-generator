from typer.testing import CliRunner

from evergreen.cli import app

runner = CliRunner()


def test_run_finishes_and_status_shows_spanish(video, adapters):
    video_id = video.name
    result = runner.invoke(app, ["run", video_id])
    assert result.exit_code == 0
    assert "script: listo" in result.output
    assert "song: listo" in runner.invoke(app, ["status", video_id]).output


def test_run_exits_1_when_a_stage_fails(video, adapters):
    adapters["song"].fail = 99
    result = runner.invoke(app, ["run", video.name])
    assert result.exit_code == 1
    assert "song: falló (RuntimeError: boom)" in result.output


def test_list_with_no_videos_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path / "nada"))
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0 and "No hay videos" in result.output


def test_list_shows_progress(video, adapters):
    runner.invoke(app, ["run", video.name])
    assert "(4/4 etapas)" in runner.invoke(app, ["list"]).output


def test_unknown_id_is_a_clear_error(video):
    for cmd in ("run", "status"):
        result = runner.invoke(app, [cmd, "no-existe"])
        assert result.exit_code == 1 and "No existe el video" in result.output
