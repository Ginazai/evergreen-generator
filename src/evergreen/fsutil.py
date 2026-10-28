"""Reemplazo de archivos tolerante a Windows/Docker: un antivirus o un reproductor pueden bloquear el destino unos instantes."""

import os
import shutil
import time
from pathlib import Path

from evergreen.errors import EvergreenError

RETRIES = 5


def replace(src, dst, sleep=time.sleep) -> None:
    for attempt in range(RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            sleep(0.3 * (attempt + 1))
    try:  # último recurso: sobrescribir el contenido (no exige renombrar sobre el destino)
        shutil.copyfile(src, dst)
        Path(src).unlink(missing_ok=True)
    except OSError as e:
        raise EvergreenError(
            f"No pude escribir {Path(dst).name}: el archivo está en uso. Ciérralo (reproductor, vista previa, "
            "antivirus) y vuelve a ejecutar; lo ya generado se conserva."
        ) from e
