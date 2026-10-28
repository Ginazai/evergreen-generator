"""Ejecuta el pipeline de un video en un proceso aparte (lo lanza la GUI) y libera el bloqueo al terminar."""

import sys
from pathlib import Path

LOCK = ".run.lock"
LOG = "run.log"


def main(video_dir: Path) -> int:
    from evergreen import cli, config, runner  # cli registra los adaptadores

    del cli
    try:
        print(f"Iniciando {video_dir.name}…", flush=True)
        config.load_settings()
        manifest = runner.run(video_dir)
        for name, st in manifest.stages.items():
            print(
                f"{name}: {st.status.value}" + (f" ({st.error})" if st.error else ""),
                flush=True,
            )
        return 0
    except Exception as e:  # noqa: BLE001 - el registro es lo que ve el usuario
        print(f"Error: {e}", flush=True)
        return 1
    finally:
        (video_dir / LOCK).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
