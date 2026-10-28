"""Llamadas a ffmpeg/ffprobe: un solo lugar para ejecutarlas y para explicar los fallos."""

import shutil
import subprocess

from evergreen.errors import EvergreenError


def require_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise EvergreenError(
            "Falta ffmpeg. Ejecuta dentro de Docker (`docker compose run --rm app ...`)."
        )


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip()[-500:]
        raise EvergreenError(f"ffmpeg falló: {tail}") from e
    except OSError as e:
        raise EvergreenError(f"No pude ejecutar ffmpeg: {e}") from e


def probe_seconds(path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            check=True, capture_output=True, text=True,
        ).stdout  # fmt: skip
        return float(out.strip())
    except (subprocess.CalledProcessError, ValueError, OSError) as e:
        raise EvergreenError(
            f"No pude leer la duración de {path}: ¿es un audio o video válido?"
        ) from e
