import pytest

from evergreen import manifest as mf
from evergreen import runner

Status = mf.Status


def stages(video):
    return mf.load(video / "manifest.yaml").stages


def test_interruption_then_rerun_skips_done_stages(video, adapters):
    adapters["song"].interrupt_once = True
    with pytest.raises(KeyboardInterrupt):
        runner.run(video)
    assert stages(video)["script"].status == Status.done
    assert stages(video)["song"].status == Status.running  # quedó a medias

    m = runner.run(video)
    assert all(s.status == Status.done for s in m.stages.values())
    assert adapters["script"].calls == 1  # no se repitió
    assert adapters["song"].calls == 2


def test_failed_stage_is_the_only_one_retried(video, adapters):
    adapters["song"].fail = 1
    first = runner.run(video)
    assert first.stages["song"].status == Status.failed
    assert "boom" in first.stages["song"].error

    second = runner.run(video)
    assert second.stages["song"].status == Status.done
    assert second.stages["song"].error is None
    assert [adapters[n].calls for n in ("script", "song", "visuals")] == [1, 2, 1]


def test_stale_running_resumes_without_manual_intervention(video, adapters):
    m = mf.load(video / "manifest.yaml")
    m.stages["script"].status = Status.running  # un proceso murió aquí
    mf.save(m, video / "manifest.yaml")
    assert all(s.status == Status.done for s in runner.run(video).stages.values())
