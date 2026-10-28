import json

import pytest
from conftest import make_audio, new_video, set_outputs, write_images
from script_samples import long_data, rhyme_data

from evergreen import manifest as mf
from evergreen.assembly.inputs import load_inputs
from evergreen.errors import EvergreenError

LONG_KEYS = [f"escena-{n}-{k}" for n in range(1, 5) for k in (1, 2)]


def load(v):
    return load_inputs(v, mf.load(v / "manifest.yaml"))


def long_video(tmp_path):
    v = new_video(
        tmp_path,
        "long",
        long_data(),
        ("script", "voice", "music", "characters", "scenes"),
    )
    voice = v / "stages/voice"
    voice.mkdir(parents=True, exist_ok=True)
    files = []
    for n in range(1, 5):
        make_audio(voice / f"escena-{n}.wav", 1)
        files.append(voice / f"escena-{n}.wav")
    timeline = voice / "timeline.json"
    timeline.write_text(
        json.dumps(
            [
                {"scene_id": f"escena-{n}", "file": f"escena-{n}.wav", "seconds": 1}
                for n in range(1, 5)
            ]
        ),
        encoding="utf-8",
    )
    set_outputs(v, "voice", [*files, timeline])
    (v / "stages/music/inbox").mkdir(parents=True, exist_ok=True)
    make_audio(v / "stages/music/inbox/music.mp3", 1)
    set_outputs(v, "music", [v / "stages/music/inbox/music.mp3"])
    write_images(v, "scenes", LONG_KEYS)
    return v


def test_long_inputs_are_found_with_per_scene_files(tmp_path):
    v = long_video(tmp_path)
    i = load(v)
    assert i.aspect == "16:9" and list(i.scene_seconds_files) == [
        f"escena-{n}" for n in range(1, 5)
    ]
    assert i.music.name == "music.mp3" and set(i.frames) == set(LONG_KEYS)
    assert i.frames["escena-1-1"].clip is None


def test_clips_are_discovered_at_render_time_and_empty_ones_ignored(tmp_path):
    v = long_video(tmp_path)
    inbox = v / "stages/scenes/inbox"
    (inbox / "escena-1-1.mp4").write_bytes(b"clip")
    (inbox / "escena-1-2.mp4").write_bytes(b"")
    i = load(v)
    assert (
        i.frames["escena-1-1"].clip is not None and i.frames["escena-1-2"].clip is None
    )


def test_manual_voice_is_a_single_file_without_timeline(tmp_path):
    v = long_video(tmp_path)
    (v / "stages/voice/inbox").mkdir(exist_ok=True)
    make_audio(v / "stages/voice/inbox/voice.mp3", 2)
    set_outputs(v, "voice", [v / "stages/voice/inbox/voice.mp3"])
    i = load(v)
    assert [p.name for p in i.voice_files] == [
        "voice.mp3"
    ] and i.scene_seconds_files == {}


def test_rhyme_inputs(tmp_path):
    v = new_video(tmp_path, "rhyme", rhyme_data(), ("script", "song", "visuals"))
    (v / "stages/song/inbox").mkdir(parents=True, exist_ok=True)
    make_audio(v / "stages/song/inbox/song.wav", 2)
    set_outputs(v, "song", [v / "stages/song/inbox/song.wav"])
    write_images(v, "visuals", ["personaje-lola", "toma-1"])
    i = load(v)
    assert i.aspect == "9:16" and i.song.name == "song.wav" and "toma-1" in i.frames


@pytest.mark.parametrize(
    ("breakage", "message"),
    [
        (
            lambda v: (v / "stages/script/script.json").unlink(),
            "script.json de la etapa `script`",
        ),
        (
            lambda v: (v / "stages/scenes/images.json").unlink(),
            "images.json de la etapa `scenes`",
        ),
        (
            lambda v: (v / "stages/scenes/escena-1-1.jpg").unlink(),
            "imagen escena-1-1.jpg",
        ),
        (
            lambda v: (v / "stages/music/inbox/music.mp3").unlink(),
            "music.mp3 de la etapa `music`",
        ),
        (lambda v: (v / "stages/voice/escena-2.wav").write_bytes(b""), "está vacío"),
    ],
)
def test_every_missing_piece_names_the_file_and_the_stage(tmp_path, breakage, message):
    v = long_video(tmp_path)
    breakage(v)
    with pytest.raises(EvergreenError, match=message):
        load(v)


def test_unfinished_stage_and_audio_less_stage_are_reported(tmp_path):
    v = long_video(tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.stages["music"].status = mf.Status.pending
    mf.save(m, v / "manifest.yaml")
    with pytest.raises(EvergreenError, match="`music` aún no está terminada"):
        load(v)
    m.stages["music"].status = mf.Status.done
    m.stages["music"].outputs = []
    mf.save(m, v / "manifest.yaml")
    with pytest.raises(EvergreenError, match="ningún audio"):
        load(v)
