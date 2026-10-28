import os

import pytest
from typer.testing import CliRunner

from evergreen import config
from evergreen.cli import app


@pytest.fixture(autouse=True)
def restore_env(monkeypatch):
    for key in config.SETTING_KEYS:
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)


def test_roundtrip_applies_and_clears_values(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "vieja")
    config.save_settings(
        {"GEMINI_API_KEY": " nueva-clave-123 ", "CLOUDFLARE_API_TOKEN": "", "OTRA": "x"}
    )
    assert config.read_settings() == {"GEMINI_API_KEY": "nueva-clave-123"}
    assert os.environ["GEMINI_API_KEY"] == "nueva-clave-123"
    assert "OTRA" not in (tmp_path / "settings.env").read_text()
    config.save_settings({})
    assert "GEMINI_API_KEY" not in os.environ and config.read_settings() == {}


def test_reader_ignores_comments_quotes_and_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    (tmp_path / "settings.env").write_text(
        '# nota\nGEMINI_API_KEY="abc"\nRARA=1\nbasura\n', encoding="utf-8"
    )
    assert config.read_settings() == {"GEMINI_API_KEY": "abc"}


def test_cli_loads_settings_over_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("EVERGREEN_VOICE_MODE", "piper")
    (tmp_path / "settings.env").write_text(
        "EVERGREEN_VOICE_MODE=manual\n", encoding="utf-8"
    )
    CliRunner().invoke(app, ["list"])
    assert os.environ["EVERGREEN_VOICE_MODE"] == "manual"


def test_mask_never_reveals_the_key():
    assert config.mask("") == "" and config.mask("corta") == "••••"
    assert config.mask("AIzaSyABCDEFGH1234") == "••••1234"
