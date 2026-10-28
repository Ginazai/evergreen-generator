import json
import wave

import pytest
from script_samples import long_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.voice_audio.piper import PAUSE_SECONDS, PiperAdapter, load_voice
from evergreen.voice_audio.voice import VoiceAdapter

RATE = 8000


class FakeVoice:
    def __init__(self):
        self.texts = []
        self.config = type("C", (), {"sample_rate": RATE})()

    def synthesize_wav(self, text, wav, set_wav_format=True):
        self.texts.append(text)
        if set_wav_format:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
        wav.writeframes(b"\x01\x00" * RATE)  # 1 s por texto


def make_video(tmp_path):
    v = project.create("Los patitos", mf.Format.long, mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.review_gates = []
    m.stages["script"].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    d = v / "stages/script"
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.json").write_text(json.dumps(long_data()), encoding="utf-8")
    return v


def run_voice(v, adapter):
    return runner.run(v, {"voice": adapter}).stages["voice"]


def test_one_wav_per_scene_with_pauses_and_timeline(tmp_path):
    v = make_video(tmp_path)
    fake = FakeVoice()
    calls = []
    state = run_voice(
        v, PiperAdapter(lambda lang, d: (calls.append((lang, d)), fake)[1])
    )
    scenes = long_data()["body"]["scenes"]
    assert state.status == mf.Status.done
    assert calls == [("es", tmp_path / "_piper")]  # se carga una sola vez
    assert len(fake.texts) == sum(len(s["beats"]) for s in scenes)
    timeline = json.loads((v / "stages/voice/timeline.json").read_text("utf-8"))
    first = scenes[0]
    expected = len(first["beats"]) + (len(first["beats"]) - 1) * PAUSE_SECONDS
    assert timeline[0]["scene_id"] == first["id"]
    assert timeline[0]["seconds"] == pytest.approx(expected, abs=0.01)
    assert state.outputs[-1] == "stages/voice/timeline.json"
    assert not list((v / "stages/voice").glob("*.part"))


def test_resume_skips_valid_scenes_and_redoes_broken_ones(tmp_path):
    v = make_video(tmp_path)
    run_voice(v, PiperAdapter(lambda *a: FakeVoice()))
    scenes = long_data()["body"]["scenes"]
    (v / f"stages/voice/{scenes[1]['id']}.wav").write_bytes(b"corrupto")
    m = mf.load(v / "manifest.yaml")
    m.stages["voice"].status = mf.Status.running  # proceso interrumpido
    mf.save(m, v / "manifest.yaml")
    fake = FakeVoice()
    run_voice(v, PiperAdapter(lambda *a: fake))
    assert len(fake.texts) == len(scenes[1]["beats"])


def test_missing_script_fails_clearly(tmp_path):
    v = project.create("X", mf.Format.long, mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.stages["script"].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    state = run_voice(v, PiperAdapter(lambda *a: FakeVoice()))
    assert state.status == mf.Status.failed and "etapa `script`" in state.error


def test_dispatcher_modes(tmp_path, monkeypatch):
    v = make_video(tmp_path)
    adapter = VoiceAdapter(PiperAdapter(lambda *a: FakeVoice()))
    assert adapter.name == "manual"
    assert run_voice(v, adapter).status == mf.Status.awaiting_manual

    monkeypatch.setenv("EVERGREEN_VOICE_MODE", "piper")
    assert adapter.name == "piper"
    assert run_voice(v, adapter).status == mf.Status.done

    monkeypatch.setenv("EVERGREEN_VOICE_MODE", "gemini")  # sin clave
    state = run_voice(make_video(tmp_path / "g"), adapter)
    assert state.status == mf.Status.failed and "GEMINI_API_KEY" in state.error

    monkeypatch.delenv("EVERGREEN_VOICE_MODE")
    monkeypatch.setenv("GEMINI_API_KEY", "k")  # con clave y sin modo: gemini
    assert adapter.name == "gemini"

    monkeypatch.setenv("EVERGREEN_VOICE_MODE", "nada")
    state = run_voice(make_video(tmp_path / "otro"), adapter)
    assert state.status == mf.Status.failed and "EVERGREEN_VOICE_MODE" in state.error


def test_real_loader_downloads_once_and_honors_piper_voice(tmp_path, monkeypatch):
    import sys
    import types

    log = []
    piper = types.ModuleType("piper")
    piper.PiperVoice = type(
        "PV",
        (),
        {"load": staticmethod(lambda p: log.append(("load", p.name)) or "voz")},
    )
    dl = types.ModuleType("piper.download_voices")
    dl.download_voice = lambda name, d: (
        log.append(("download", name)),
        (d / f"{name}.onnx").write_bytes(b"x"),
    )
    monkeypatch.setitem(sys.modules, "piper", piper)
    monkeypatch.setitem(sys.modules, "piper.download_voices", dl)
    monkeypatch.setenv("PIPER_VOICE", "es_MX-otra-medium")
    assert load_voice("es", tmp_path / "v") == "voz"
    assert load_voice("es", tmp_path / "v") == "voz"
    assert log == [
        ("download", "es_MX-otra-medium"),
        ("load", "es_MX-otra-medium.onnx"),
        ("load", "es_MX-otra-medium.onnx"),
    ]


def test_missing_piper_package_gives_a_clear_message(tmp_path, monkeypatch):
    import sys

    from evergreen.errors import EvergreenError

    monkeypatch.setitem(sys.modules, "piper", None)  # fuerza ImportError
    with pytest.raises(EvergreenError, match="piper-tts"):
        load_voice("es", tmp_path)


def test_wave_module_is_the_format_we_write(tmp_path):
    p = tmp_path / "a.wav"
    PiperAdapter._synthesize(FakeVoice(), ["uno"], p)
    with wave.open(str(p)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, RATE)
