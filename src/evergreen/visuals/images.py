"""Lectura mínima de PNG/JPEG/WebP: tipo y tamaño, para validar lo que devuelve un generador."""

import struct


def image_info(data: bytes) -> tuple[str, int, int] | None:
    """(tipo, ancho, alto) o None si no es una imagen reconocible."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return "jpeg", w, h
            i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and data[12:16] == b"VP8X":
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return "webp", w, h
    return None


def shrink(path, max_side: int = 448) -> bytes:
    """Reduce una imagen a menos de 512 px por lado (límite de las referencias) con ffmpeg."""
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ref.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf",
                 f"scale={max_side}:{max_side}:force_original_aspect_ratio=decrease",
                 "-q:v", "3", str(out)],
                check=True, capture_output=True,
            )  # fmt: skip
        except (OSError, subprocess.CalledProcessError) as e:
            raise RuntimeError(f"No pude reducir la referencia con ffmpeg: {e}") from e
        return out.read_bytes()
