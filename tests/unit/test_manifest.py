import os
from datetime import datetime

import pytest
from pydantic import ValidationError

from evergreen import manifest
from evergreen.manifest import Manifest, StageState, Status


def make(title="El ñandú canción") -> Manifest:
    return Manifest(
        id="x",
        title=title,
        format="rhyme",
        created_at=datetime(2026, 10, 20, 14, 0),
        review_gates=["script"],
        stages={"script": StageState(status=Status.done, outputs=["a.md"])},
    )


def test_round_trip_keeps_accents(tmp_path):
    path = tmp_path / "manifest.yaml"
    original = make()
    manifest.save(original, path)
    assert manifest.load(path) == original
    assert "El ñandú canción" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "bad", [{"format": "movie"}, {"stages": {"s": {"status": "bogus"}}}, {"title": ""}]
)
def test_invalid_values_rejected(bad):
    data = make().model_dump(mode="json") | bad
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_gate_must_be_a_stage():
    data = make().model_dump(mode="json") | {"review_gates": ["voice"]}
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_unknown_fields_rejected():
    data = make().model_dump(mode="json") | {"api_key": "sk-123"}
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_failed_write_keeps_previous_manifest(tmp_path, monkeypatch):
    path = tmp_path / "manifest.yaml"
    manifest.save(make("Original"), path)

    def boom(*_):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        manifest.save(make("Nuevo"), path)

    assert manifest.load(path).title == "Original"
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.yaml"]


def test_manifest_without_brief_still_loads(tmp_path):
    """Un manifest escrito antes de existir `brief` sigue siendo válido."""
    path = tmp_path / "manifest.yaml"
    manifest.save(make(), path)
    text = "".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines(True)
        if "brief" not in line
    )
    path.write_text(text, encoding="utf-8")
    assert manifest.load(path).brief is None
