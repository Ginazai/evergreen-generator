import json

from script_samples import long_data, rhyme_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.voice_audio import register
from evergreen.voice_audio.manual import AudioManualAdapter, music_prompt, song_prompt


def video(tmp_path, fmt, data=None):
    v = project.create("Los patitos", mf.Format(fmt), mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.review_gates = []
    for name, st in m.stages.items():
        if name == "script":
            st.status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    d = v / "stages/script"
    d.mkdir(parents=True, exist_ok=True)
    if data:
        (d / "script.json").write_text(json.dumps(data), encoding="utf-8")
    return v


def run(v, stage, adapter):
    return runner.run(v, {"script": None, stage: adapter}).stages[stage]


def test_song_prompt_has_style_and_tagged_lyrics():
    from evergreen.script_writer.models import parse_script

    s = parse_script(json.dumps(rhyme_data()), "rhyme", mf.Language.es)
    text = song_prompt(s)
    assert "folk infantil alegre" in text and "100 bpm" in text
    assert "[Verse]\nuno\ndos" in text and "[Chorus]" in text


def test_song_stage_asks_then_accepts_mp3_or_wav(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data())
    adapter = AudioManualAdapter("song", song_prompt)
    state = run(v, "song", adapter)
    assert state.status == mf.Status.awaiting_manual
    assert "[Chorus]" in (v / "stages/song/MANUAL.md").read_text("utf-8")
    (v / "stages/song/inbox/song.wav").write_bytes(b"RIFF....")
    state = run(v, "song", adapter)
    assert state.status == mf.Status.done
    assert state.outputs == ["stages/song/inbox/song.wav"]
    assert not (v / "stages/song/MANUAL.md").exists()


def test_empty_audio_is_reported_in_manual_md(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data())
    (v / "stages/song/inbox").mkdir(parents=True)
    (v / "stages/song/inbox/song.mp3").write_bytes(b"")
    state = run(v, "song", AudioManualAdapter("song", song_prompt))
    assert state.status == mf.Status.awaiting_manual
    assert "vacío" in (v / "stages/song/MANUAL.md").read_text("utf-8")


def test_music_prompt_uses_tone_and_logline(tmp_path):
    from evergreen.script_writer.models import parse_script

    s = parse_script(json.dumps(long_data()), "long", mf.Language.es)
    assert s.variation.tone in music_prompt(s) and s.body.logline in music_prompt(s)


def test_missing_script_is_a_clear_error(tmp_path):
    v = video(tmp_path, "rhyme")
    state = run(v, "song", AudioManualAdapter("song", song_prompt))
    assert state.status == mf.Status.failed and "etapa `script`" in state.error


def test_register_adds_song_and_music():
    from evergreen import registry

    register()
    assert {"song", "music"} <= set(registry.ADAPTERS)
