import json
import shutil
import subprocess

import pytest

from evergreen import manifest as mf
from evergreen import project

needs_ffmpeg = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg no está instalado"
)


def make_image(path, w=320, h=180, color="blue"):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}",
         "-frames:v", "1", str(path)],
        check=True,
    )  # fmt: skip


def make_audio(path, seconds, freq=440):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={seconds}", "-ar", "24000", "-ac", "1", str(path)],
        check=True,
    )  # fmt: skip


def new_video(tmp_path, fmt, data, done, aspect=None):
    v = project.create(
        "Los patitos", mf.Format(fmt), mf.Language.es, tmp_path, aspect=aspect
    )
    m = mf.load(v / "manifest.yaml")
    m.review_gates = []
    for name in done:
        m.stages[name].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    (v / "stages/script").mkdir(parents=True, exist_ok=True)
    (v / "stages/script/script.json").write_text(json.dumps(data), encoding="utf-8")
    return v


def set_outputs(v, stage, files):
    m = mf.load(v / "manifest.yaml")
    m.stages[stage].outputs = [f.relative_to(v).as_posix() for f in files]
    mf.save(m, v / "manifest.yaml")


def write_images(v, stage, keys, clips=()):
    d = v / "stages" / stage
    d.mkdir(parents=True, exist_ok=True)
    (d / "inbox").mkdir(exist_ok=True)
    entries = []
    for key in keys:
        make_image(d / f"{key}.jpg")
        entries.append({"key": key, "image": f"{key}.jpg", "clip": None})
    (d / "images.json").write_text(json.dumps(entries), encoding="utf-8")
    return d
