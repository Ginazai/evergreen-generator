"""Lanzar y vigilar la ejecución de un video desde la GUI: un proceso por video, con bloqueo y registro."""

import os
import subprocess
import sys
from pathlib import Path

from evergreen.errors import EvergreenError
from evergreen.jobrun import LOCK, LOG

_children: list[subprocess.Popen] = []


def _alive(pid: int) -> bool:
    for child in _children[
        :
    ]:  # cosecha a los hijos terminados (si no, quedan zombis y parecen vivos)
        if child.poll() is not None:
            _children.remove(child)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # tras reiniciar el contenedor el pid puede ser de otro proceso: debe ser nuestro trabajo
        return b"evergreen.jobrun" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return True  # sin /proc (no Linux): nos fiamos del pid


def is_running(video_dir: Path) -> bool:
    lock = video_dir / LOCK
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        return False
    if _alive(pid):
        return True
    lock.unlink(missing_ok=True)  # el proceso murió sin limpiar
    return False


def start(video_dir: Path) -> None:
    if is_running(video_dir):
        raise EvergreenError("Este video ya se está ejecutando.")
    log = open(video_dir / LOG, "w", encoding="utf-8")  # noqa: SIM115 - lo hereda el hijo
    env = {**os.environ, "EVERGREEN_PROJECTS_DIR": str(video_dir.parent)}
    child = subprocess.Popen(
        [sys.executable, "-m", "evergreen.jobrun", str(video_dir)],
        stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True,
    )  # fmt: skip
    log.close()
    _children.append(child)
    (video_dir / LOCK).write_text(str(child.pid))


def read_log(video_dir: Path, lines: int = 40) -> str:
    try:
        return "\n".join(
            (video_dir / LOG).read_text(encoding="utf-8").splitlines()[-lines:]
        )
    except OSError:
        return ""
