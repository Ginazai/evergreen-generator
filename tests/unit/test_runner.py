from evergreen import manifest as mf
from evergreen import runner

Status = mf.Status


def stages(video):
    return mf.load(video / "manifest.yaml").stages


def test_three_plus_stages_run_in_order_and_finish(video, adapters):
    m = runner.run(video)
    assert all(s.status == Status.done for s in m.stages.values())
    assert stages(video)["song"].outputs == ["stages/song/out.txt"]
    assert (video / "stages" / "song" / "out.txt").read_text(encoding="utf-8") == "song"


def test_state_is_saved_before_next_stage(video, adapters):
    runner.run(video)
    seen = adapters["visuals"].seen  # disco justo antes de ejecutar `visuals`
    assert seen["script"] == Status.done and seen["song"] == Status.done
    assert seen["visuals"] == Status.running


def test_unexpected_error_does_not_corrupt_manifest(video, adapters):
    adapters["song"].fail = 99
    m = runner.run(video)
    assert m.stages["song"].status == Status.failed
    assert stages(video)["song"].error == "RuntimeError: boom"
    assert stages(video)["visuals"].status == Status.pending


def test_stage_without_adapter_falls_back_to_manual(video, adapters):
    del adapters["song"]
    m = runner.run(video)
    assert m.stages["song"].status == Status.awaiting_manual
    assert m.stages["song"].adapter == "manual"
    assert (video / "stages" / "song" / "MANUAL.md").is_file()


def test_manual_result_stops_the_pipeline(video, adapters):
    adapters["song"].manual = True
    m = runner.run(video)
    assert m.stages["song"].status == Status.awaiting_manual
    assert adapters["visuals"].calls == 0
