import struct

from evergreen.visuals.images import image_info


def png(w, h):
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", w, h)
        + b"\x08\x02\x00\x00\x00"
    )


def jpeg(w, h):
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = (
        b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", h, w)
        + b"\x03"
        + b"\x00" * 9
    )
    return b"\xff\xd8" + app0 + sof


def webp(w, h):
    return (
        b"RIFF\x00\x00\x00\x00WEBPVP8X"
        + b"\x0a\x00\x00\x00"
        + b"\x00" * 4
        + (w - 1).to_bytes(3, "little")
        + (h - 1).to_bytes(3, "little")
    )


def test_reads_type_and_size():
    assert image_info(png(1280, 720)) == ("png", 1280, 720)
    assert image_info(jpeg(1024, 768)) == ("jpeg", 1024, 768)
    assert image_info(webp(640, 360)) == ("webp", 640, 360)


def test_garbage_and_truncated_data_give_none():
    for data in (
        b"",
        b"hola",
        b"\xff\xd8",
        b"\xff\xd8\x00\x00",
        b"\x89PNG\r\n\x1a\n",
        jpeg(1, 1)[:10],
    ):
        assert image_info(data) is None


def test_shrink_reduces_with_ffmpeg_and_reports_failures(tmp_path):
    import shutil
    import subprocess

    import pytest

    from evergreen.visuals.images import shrink

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg no está instalado")
    src = tmp_path / "a.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=yellow:s=768x512",
         "-frames:v", "1", str(src)],
        check=True,
    )  # fmt: skip
    kind, w, h = image_info(shrink(src))
    assert kind == "jpeg" and max(w, h) <= 448 and w > h
    with pytest.raises(RuntimeError, match="ffmpeg"):
        shrink(tmp_path / "no-existe.jpg")
