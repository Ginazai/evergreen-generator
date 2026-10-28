import pytest

from evergreen import config


@pytest.fixture(autouse=True)
def restore_settings_env(monkeypatch):
    """load_settings escribe en os.environ: se registra el estado previo para que no se filtre a otras pruebas."""
    for key in config.SETTING_KEYS:
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
