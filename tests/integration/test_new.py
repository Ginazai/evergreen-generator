import time

import pytest
from typer.testing import CliRunner

from evergreen import manifest
from evergreen.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def projects(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    return tmp_path


def test_new_creates_valid_manifest_fast(projects):
    start = time.perf_counter()
    result = runner.invoke(app, ["new", "El ñandú canción", "--format", "rhyme"])
    assert time.perf_counter() - start < 1
    assert result.exit_code == 0
    (folder,) = projects.iterdir()
    m = manifest.load(folder / "manifest.yaml")
    assert m.title == "El ñandú canción"
    assert m.id == folder.name and folder.name.startswith("el-nandu-cancion-")
    assert list(m.stages) == ["script", "song", "visuals", "assembly"]
    assert all(s.status == manifest.Status.pending for s in m.stages.values())
    assert m.review_gates == ["script", "song"]
    assert (folder / "stages" / "song").is_dir()


def test_long_format_has_its_own_stages_and_gates(projects):
    runner.invoke(app, ["new", "Aventura", "--format", "long"])
    (folder,) = projects.iterdir()
    m = manifest.load(folder / "manifest.yaml")
    assert list(m.stages) == [
        "script",
        "voice",
        "music",
        "characters",
        "scenes",
        "assembly",
    ]
    assert m.review_gates == ["script", "voice", "characters", "scenes"]


def test_same_title_same_day_gets_suffix(projects):
    for _ in range(2):
        assert runner.invoke(app, ["new", "Patitos", "--format", "long"]).exit_code == 0
    names = sorted(p.name for p in projects.iterdir())
    assert len(names) == 2 and names[1].endswith("-2")


@pytest.mark.parametrize(
    "args",
    [
        ["new", "Patitos", "--format", "movie"],
        ["new", "   ", "--format", "rhyme"],
        ["new", "!!!", "--format", "rhyme"],
    ],
)
def test_invalid_input_creates_nothing(projects, args):
    assert runner.invoke(app, args).exit_code != 0
    assert list(projects.iterdir()) == []


def test_language_option(projects):
    runner.invoke(app, ["new", "Ducks", "--format", "rhyme", "--language", "en"])
    (folder,) = projects.iterdir()
    assert manifest.load(folder / "manifest.yaml").language == manifest.Language.en


def test_brief_is_saved(projects):
    result = runner.invoke(
        app,
        [
            "new",
            "Patitos",
            "--format",
            "rhyme",
            "--brief",
            "  patitos que aprenden a nadar  ",
        ],
    )
    assert result.exit_code == 0
    (folder,) = projects.iterdir()
    assert (
        manifest.load(folder / "manifest.yaml").brief == "patitos que aprenden a nadar"
    )


@pytest.mark.parametrize("brief", [None, "", "   "])
def test_missing_or_blank_brief_is_none(projects, brief):
    args = ["new", "Patitos", "--format", "rhyme"] + (
        [] if brief is None else ["--brief", brief]
    )
    assert runner.invoke(app, args).exit_code == 0
    (folder,) = projects.iterdir()
    assert manifest.load(folder / "manifest.yaml").brief is None


def test_too_long_brief_creates_nothing(projects):
    result = runner.invoke(
        app, ["new", "Patitos", "--format", "rhyme", "--brief", "x" * 501]
    )
    assert result.exit_code == 1 and "500" in result.output
    assert list(projects.iterdir()) == []


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--format", "long"], "16:9"),
        (["--format", "rhyme"], "9:16"),
        (["--format", "long", "--aspect", "9:16"], "9:16"),
    ],
)
def test_aspect_defaults_by_format_and_can_be_overridden(projects, args, expected):
    assert runner.invoke(app, ["new", "Video", *args]).exit_code == 0
    (folder,) = projects.iterdir()
    assert manifest.aspect_of(manifest.load(folder / "manifest.yaml")) == expected


def test_invalid_aspect_is_rejected(projects):
    result = runner.invoke(app, ["new", "V", "--format", "long", "--aspect", "4:3"])
    assert result.exit_code != 0 and not list(projects.iterdir())
