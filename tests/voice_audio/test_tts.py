import json

import pytest
from gemini_fakes import FakeTtsSDK, api_error, wav_bytes
from script_samples import long_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.errors import EvergreenError
from evergreen.voice_audio.gemini_voice import DEFAULT_TTS_MODEL, GeminiVoiceAdapter
from evergreen.voice_audio.requests import Turn, VoiceRequest
from evergreen.voice_audio.tts import PACE_SECONDS, QuotaExceeded, TtsClient

KEY = "clave-secreta-123"
VOICES = {"narrator": "Charon", "lola": "Puck", "pipo": "Kore"}


class Clock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def __call__(self):
        return self.now


def client(*script, **kw):
    sdk, clock = FakeTtsSDK(*script), Clock()
    return (
        TtsClient(KEY, "m", sdk=sdk, sleep=clock.sleep, clock=clock, **kw),
        sdk,
        clock,
    )


def req(*speakers):
    return VoiceRequest(
        "a", "a", tuple(Turn(s, f"hola {s}", "alegre") for s in speakers)
    )


def test_one_voice_uses_a_list_and_two_voices_use_speakers():
    c, sdk, _ = client(wav_bytes(), wav_bytes())
    c.speak(req("lola"), VOICES)
    c.speak(req("lola", "pipo"), VOICES)
    one, two = sdk.interactions.requests
    assert one["model"] == "m" and one["response_format"] == {"type": "audio"}
    assert one["generation_config"]["speech_config"] == [{"voice": "Puck"}]
    assert two["generation_config"]["speech_config"] == {
        "speakers": [
            {"speaker": "lola", "voice": "Puck"},
            {"speaker": "pipo", "voice": "Kore"},
        ]
    }
    note = two["input"][0]["content"][1]["annotations"][0]
    assert note == {"type": "speech_metadata", "speaker": "pipo", "style": "alegre"}


def test_returns_wav_bytes_and_paces_requests():
    c, _, clock = client(wav_bytes(), wav_bytes())
    assert c.speak(req("lola"), VOICES)[:4] == b"RIFF"
    c.speak(req("lola"), VOICES)
    assert clock.sleeps == [PACE_SECONDS]  # la 2.ª espera lo que falta del minuto


def test_per_minute_limit_is_retried_but_daily_quota_is_not():
    c, _, clock = client(api_error(429, message="rate"), wav_bytes())
    c.speak(req("lola"), VOICES)
    assert c.calls == 2 and 25 in clock.sleeps
    d, _, _ = client(api_error(429, message="exceeded GenerateRequestsPerDay"))
    with pytest.raises(QuotaExceeded, match="medianoche"):
        d.speak(req("lola"), VOICES)
    assert d.calls == 1


def test_retries_run_out_and_cap_is_enforced():
    c, _, _ = client(*[api_error(503)] * 5)
    with pytest.raises(EvergreenError, match="Error de Gemini TTS"):
        c.speak(req("lola"), VOICES)
    assert c.calls == 3  # 1 + 2 reintentos
    capped, _, _ = client(wav_bytes(), wav_bytes(), max_calls=1)
    capped.speak(req("lola"), VOICES)
    with pytest.raises(QuotaExceeded, match="tope de 1"):
        capped.speak(req("lola"), VOICES)


def test_key_is_never_shown_and_auth_errors_are_clear():
    c, _, _ = client(api_error(500, message=f"fallo con {KEY}"))
    with pytest.raises(EvergreenError) as e:
        c.speak(req("lola"), VOICES)
    assert KEY not in str(e.value)
    d, _, _ = client(api_error(403))
    with pytest.raises(EvergreenError, match="GEMINI_API_KEY"):
        d.speak(req("lola"), VOICES)


def test_missing_audio_is_an_error():
    c, _, _ = client(None)
    with pytest.raises(EvergreenError, match="no devolvió audio"):
        c.speak(req("lola"), VOICES)


# --- adaptador --------------------------------------------------------------------------------


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


def adapter(*script, **kw):
    sdk, clock = FakeTtsSDK(*script), Clock()
    made = []

    def factory(key, model):
        made.append((key, model))
        return TtsClient(key, model, sdk=sdk, sleep=clock.sleep, clock=clock, **kw)

    return GeminiVoiceAdapter(factory), sdk, made


def run(v, a):
    return runner.run(v, {"voice": a}).stages["voice"]


def test_full_run_writes_wavs_timeline_and_uses_key_and_default_model(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    v = make_video(tmp_path)
    n = len(long_data()["body"]["scenes"])
    a, sdk, made = adapter(*[wav_bytes(2)] * 20)
    state = run(v, a)
    assert state.status == mf.Status.done and made == [(KEY, DEFAULT_TTS_MODEL)]
    timeline = json.loads((v / "stages/voice/timeline.json").read_text("utf-8"))
    assert len(timeline) == len(sdk.interactions.requests) >= n
    assert all(e["seconds"] == pytest.approx(2) for e in timeline)
    assert state.outputs[-1] == "stages/voice/timeline.json"


def test_quota_mid_run_keeps_done_scenes_and_resumes_without_repeating(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    v = make_video(tmp_path)
    a, _, _ = adapter(wav_bytes(), api_error(429, message="PerDay"))
    state = run(v, a)
    assert state.status == mf.Status.failed
    assert "Se generaron 1 de" in state.error and "retoma" in state.error
    assert len(list((v / "stages/voice").glob("*.wav"))) == 1

    b, sdk2, _ = adapter(*[wav_bytes()] * 20)
    state = run(v, b)
    total = len(json.loads((v / "stages/voice/timeline.json").read_text("utf-8")))
    assert state.status == mf.Status.done
    assert len(sdk2.interactions.requests) == total - 1  # no repite la ya hecha


def test_invalid_audio_is_rejected_and_not_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    v = make_video(tmp_path)
    a, _, _ = adapter(b"esto no es un wav")
    state = run(v, a)
    assert state.status == mf.Status.failed and "WAV válido" in state.error
    assert not list((v / "stages/voice").glob("*.part"))


def test_missing_script_fails_clearly(tmp_path):
    v = project.create("X", mf.Format.long, mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.stages["script"].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    a, _, _ = adapter()
    assert "etapa `script`" in run(v, a).error


def test_dispatcher_routes_to_gemini_when_there_is_a_key(tmp_path, monkeypatch):
    from evergreen.voice_audio.voice import VoiceAdapter

    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    v = make_video(tmp_path)
    a, sdk, _ = adapter(*[wav_bytes()] * 20)
    assert run(v, VoiceAdapter(gemini=a)).status == mf.Status.done
    assert sdk.interactions.requests


def test_timeout_is_a_clear_error_not_a_hang():
    import httpx

    c, _, _ = client(httpx.ReadTimeout("lento"))
    with pytest.raises(EvergreenError, match="no respondió") as e:
        c.speak(req("narrator"), VOICES)
    assert KEY not in str(e.value)
