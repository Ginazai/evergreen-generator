import pytest

from evergreen import fsutil
from evergreen.errors import EvergreenError


def test_retries_then_succeeds(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.part", tmp_path / "a.wav"
    src.write_text("x")
    calls = []

    def flaky(s, d):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError
        src.rename(d)

    monkeypatch.setattr(fsutil.os, "replace", flaky)
    fsutil.replace(src, dst, sleep=lambda _: None)
    assert dst.read_text() == "x" and len(calls) == 3


def test_falls_back_to_copy_and_then_explains(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.part", tmp_path / "a.wav"
    src.write_text("nuevo")
    dst.write_text("viejo")
    monkeypatch.setattr(
        fsutil.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError)
    )
    fsutil.replace(src, dst, sleep=lambda _: None)
    assert dst.read_text() == "nuevo" and not src.exists()
    src.write_text("otra")
    monkeypatch.setattr(
        fsutil.shutil, "copyfile", lambda s, d: (_ for _ in ()).throw(PermissionError)
    )
    with pytest.raises(EvergreenError, match="en uso"):
        fsutil.replace(src, dst, sleep=lambda _: None)
