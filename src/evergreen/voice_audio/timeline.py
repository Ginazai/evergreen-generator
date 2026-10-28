import io
import json
import wave
from pathlib import Path


def wav_seconds(path: Path) -> float:
    with wave.open(io.BytesIO(path.read_bytes())) as w:
        return w.getnframes() / w.getframerate()


def is_valid_wav(path: Path) -> bool:
    try:
        return path.is_file() and wav_seconds(path) > 0
    except (wave.Error, EOFError, OSError):
        return False


def write_timeline(stage_dir: Path, entries: list[dict]) -> Path:
    """Un registro por archivo de audio: lo que el montaje necesita para ordenar y medir."""
    path = stage_dir / "timeline.json"
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
