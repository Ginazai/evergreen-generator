from evergreen import manifest as mf
from evergreen import registry
from evergreen.adapters.base import Done, NeedsManual, StageContext
from evergreen.adapters.manual import ManualAdapter


def ctx(video):
    stage_dir = video / "stages" / "script"
    return StageContext("script", stage_dir, video, mf.load(video / "manifest.yaml"))


def test_lists_only_missing_files_and_finishes_when_complete(video):
    adapter, c = ManualAdapter(["a.txt", "b.txt"]), ctx(video)
    manual = c.stage_dir / "MANUAL.md"

    first = adapter.run(c)
    assert isinstance(first, NeedsManual) and first.expected_files == ["a.txt", "b.txt"]

    (c.stage_dir / "inbox" / "a.txt").write_text("x", encoding="utf-8")
    second = adapter.run(c)
    assert second.expected_files == ["b.txt"]
    text = manual.read_text(encoding="utf-8")
    assert (
        "b.txt" in text
        and "a.txt" not in text
        and f"evergreen run {video.name}" in text
    )

    (c.stage_dir / "inbox" / "b.txt").write_text("y", encoding="utf-8")
    done = adapter.run(c)
    assert isinstance(done, Done) and len(done.outputs) == 2
    assert not manual.exists()


def test_every_stage_has_default_manual_files():
    for stages in registry.STAGES.values():
        assert all(registry.MANUAL_FILES[s] for s in stages)
