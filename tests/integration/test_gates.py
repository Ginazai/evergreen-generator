from typer.testing import CliRunner

from evergreen import manifest as mf
from evergreen import project
from evergreen.cli import app

runner = CliRunner()
Status = mf.Status


def stages(video):
    return mf.load(video / "manifest.yaml").stages


def set_gates(video, gates):
    m = mf.load(video / "manifest.yaml")
    m.review_gates = gates
    mf.save(m, video / "manifest.yaml")


def test_gate_stops_then_approval_continues(video, adapters):
    set_gates(video, ["song"])
    result = runner.invoke(app, ["run", video.name])
    assert result.exit_code == 0 and "song: esperando aprobación" in result.output
    assert adapters["visuals"].calls == 0

    runner.invoke(app, ["run", video.name])  # sigue detenido sin aprobar
    assert adapters["visuals"].calls == 0 and adapters["song"].calls == 1

    assert runner.invoke(app, ["approve", video.name, "song"]).exit_code == 0
    runner.invoke(app, ["run", video.name])
    assert all(s.status == Status.done for s in stages(video).values())
    assert adapters["song"].calls == 1  # aprobar no repite la etapa


def test_approving_a_stage_not_awaiting_changes_nothing(video, adapters):
    before = stages(video)
    for stage in ("song", "no-existe"):
        result = runner.invoke(app, ["approve", video.name, stage])
        assert result.exit_code == 1 and "Error:" in result.output
    assert stages(video) == before


def test_no_gates_means_no_pause(video, adapters):
    runner.invoke(app, ["run", video.name])
    assert not any(s.status == Status.awaiting_approval for s in stages(video).values())


def test_default_gates_pause_right_after_script(tmp_path, monkeypatch, adapters):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    video = project.create("Patitos", mf.Format.rhyme, mf.Language.es, tmp_path)
    runner.invoke(app, ["run", video.name])
    assert stages(video)["script"].status == Status.awaiting_approval
    assert stages(video)["song"].status == Status.pending
