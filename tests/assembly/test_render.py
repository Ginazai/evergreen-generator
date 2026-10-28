import json
import subprocess

import pytest
from conftest import (
    make_audio,
    make_image,
    needs_ffmpeg,
    new_video,
    set_outputs,
    write_images,
)
from script_samples import rhyme_data
from test_inputs import LONG_KEYS, long_video

from evergreen import manifest as mf
from evergreen.adapters.base import Done, StageContext
from evergreen.assembly import render
from evergreen.assembly.adapter import AssemblyAdapter
from evergreen.assembly.ffmpeg import probe_seconds
from evergreen.assembly.inputs import Frame
from evergreen.errors import EvergreenError

pytestmark = needs_ffmpeg
SMALL = {"16:9": (192, 108), "9:16": (108, 192)}


def ctx_for(v, stage="assembly"):
    m = mf.load(v / "manifest.yaml")
    d = v / "stages" / stage
    d.mkdir(parents=True, exist_ok=True)
    return StageContext(stage, d, v, m)


def streams(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return json.loads(out)["streams"]


@pytest.mark.parametrize("direction", render.DIRECTIONS)
def test_segment_has_requested_duration_and_is_cached(tmp_path, direction):
    img = tmp_path / "a.png"
    make_image(img)
    f = Frame("k", img, None)
    seg = render.segment(f, 1.2, direction, (192, 108), tmp_path)
    assert probe_seconds(seg) == pytest.approx(1.2, abs=0.1)
    assert render.segment(f, 1.2, direction, (192, 108), tmp_path) == seg


def test_clip_shorter_than_shot_holds_last_frame(tmp_path):
    img, clip = tmp_path / "a.png", tmp_path / "c.mp4"
    make_image(img)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=0.5", str(clip)],
        check=True,
    )  # fmt: skip
    seg = render.segment(Frame("k", img, clip), 2.0, "in", (192, 108), tmp_path)
    assert probe_seconds(seg) == pytest.approx(2.0, abs=0.15)


def test_long_video_end_to_end(tmp_path):
    v = long_video(tmp_path)
    (v / "stages/scenes/inbox/escena-1-1.mp4").write_bytes(b"")  # vacío: se ignora
    result = AssemblyAdapter(SMALL).run(ctx_for(v))
    assert isinstance(result, Done) and [p.name for p in result.outputs] == [
        "final.mp4",
        "assembly.json",
    ]
    final = result.outputs[0]
    kinds = {s["codec_type"]: s for s in streams(final)}
    assert (kinds["video"]["width"], kinds["video"]["height"]) == SMALL[
        "16:9"
    ] and "audio" in kinds
    assert probe_seconds(final) == pytest.approx(4.0, abs=0.3)  # 4 escenas de 1 s
    info = json.loads(result.outputs[1].read_text(encoding="utf-8"))
    assert [s["key"] for s in info["shots"]] == LONG_KEYS and info["aspect"] == "16:9"


def test_second_run_reuses_segments(tmp_path):
    v = long_video(tmp_path)
    c = ctx_for(v)
    AssemblyAdapter(SMALL).run(c)
    first = {p: p.stat().st_mtime_ns for p in (c.stage_dir / "work").glob("seg-*.mp4")}
    AssemblyAdapter(SMALL).run(c)
    assert first and all(p.stat().st_mtime_ns == t for p, t in first.items())


def test_manual_voice_without_timeline(tmp_path):
    v = long_video(tmp_path)
    (v / "stages/voice/inbox").mkdir(exist_ok=True)
    make_audio(v / "stages/voice/inbox/voice.mp3", 4)
    set_outputs(v, "voice", [v / "stages/voice/inbox/voice.mp3"])
    final = AssemblyAdapter(SMALL).run(ctx_for(v)).outputs[0]
    assert probe_seconds(final) == pytest.approx(4.0, abs=0.3)


def test_rhyme_is_vertical_and_uses_only_the_song(tmp_path):
    v = new_video(tmp_path, "rhyme", rhyme_data(), ("script", "song", "visuals"))
    (v / "stages/song/inbox").mkdir(parents=True, exist_ok=True)
    make_audio(v / "stages/song/inbox/song.wav", 3)
    set_outputs(v, "song", [v / "stages/song/inbox/song.wav"])
    write_images(v, "visuals", ["personaje-lola", "toma-1"])
    final = AssemblyAdapter(SMALL).run(ctx_for(v)).outputs[0]
    video = next(s for s in streams(final) if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == SMALL["9:16"]
    assert probe_seconds(final) == pytest.approx(3.0, abs=0.3)


def test_missing_shot_image_and_voice_scene_are_clear_errors(tmp_path):
    v = long_video(tmp_path)
    (v / "stages/scenes/images.json").write_text(
        json.dumps([{"key": "escena-1-1", "image": "escena-1-1.jpg", "clip": None}]),
        encoding="utf-8",
    )
    with pytest.raises(EvergreenError, match="Falta la imagen escena-1-2"):
        AssemblyAdapter(SMALL).run(ctx_for(v))
    v2 = long_video(tmp_path / "otro")
    t = v2 / "stages/voice/timeline.json"
    t.write_text(
        json.dumps([{"scene_id": "escena-1", "file": "escena-1.wav", "seconds": 1}]),
        encoding="utf-8",
    )
    with pytest.raises(EvergreenError, match="escena escena-2"):
        AssemblyAdapter(SMALL).run(ctx_for(v2))


def test_ffmpeg_failure_is_reported(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"no soy una imagen")
    with pytest.raises(EvergreenError, match="ffmpeg falló"):
        render.segment(Frame("k", bad, None), 1, "in", (192, 108), tmp_path)
