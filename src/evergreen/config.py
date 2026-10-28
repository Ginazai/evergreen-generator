import os
import tempfile
from pathlib import Path

from evergreen import fsutil

# Valores que la GUI puede editar; viven en <proyectos>/settings.env (el contenedor no ve el .env de Windows).
SETTING_KEYS = (
    "GEMINI_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "EVERGREEN_VOICE_MODE",
    "EVERGREEN_IMAGE_MODE",
)
SECRET_KEYS = {"GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN"}


def projects_dir() -> Path:
    return Path(os.environ.get("EVERGREEN_PROJECTS_DIR", "projects"))


def settings_path() -> Path:
    return projects_dir() / "settings.env"


def read_settings() -> dict[str, str]:
    path = settings_path()
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        value = value.strip().strip("\"'")
        if sep and key in SETTING_KEYS and value:
            out[key] = value
    return out


def load_settings() -> None:
    """Los valores del archivo tienen prioridad sobre las variables de entorno."""
    os.environ.update(read_settings())


def save_settings(values: dict[str, str]) -> None:
    """Reemplaza el archivo con los valores no vacíos y los aplica de inmediato."""
    clean = {k: v.strip() for k, v in values.items() if k in SETTING_KEYS and v.strip()}
    for key in SETTING_KEYS:
        if key not in clean:
            os.environ.pop(key, None)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"{k}={v}\n" for k, v in clean.items()))
        fsutil.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    load_settings()


def mask(value: str) -> str:
    """Para mostrar una clave sin revelarla: solo los últimos 4 caracteres."""
    return "" if not value else "••••" + value[-4:] if len(value) > 8 else "••••"
