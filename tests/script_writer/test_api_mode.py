import json

import pytest
from gemini_fakes import FakeSDK, api_error
from script_samples import long_data, rhyme_data

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.script_writer.adapter import DEFAULT_MODEL, ScriptAdapter
from evergreen.script_writer.gemini import GeminiClient

KEY = "fake-key-123"
SAMPLES = {"rhyme": rhyme_data, "long": long_data}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)


def adapter_with(*script):
    sdk = FakeSDK(*script)
    factory = lambda k, model: GeminiClient(k, model, sdk=sdk, sleep=lambda s: None)
    return ScriptAdapter(client_factory=factory), sdk


def make_video(tmp_path, monkeypatch, fmt="rhyme", language="es"):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    video = project.create(
        "Los patitos", mf.Format(fmt), mf.Language(language), tmp_path
    )
    m = mf.load(video / "manifest.yaml")
    m.review_gates = []
    mf.save(m, video / "manifest.yaml")
    return video


def run_script(video, adapter):
    return runner.run(video, {"script": adapter}).stages["script"]


def dumps(data):
    return json.dumps(data, ensure_ascii=False)


def different_rhyme(tag="x"):
    data = rhyme_data()
    data["body"]["sections"] = [
        {
            "kind": "verse",
            "lines": [f"{tag}{n} palabra{tag}{n} nueva{n}" for n in range(12)],
        }
    ]
    return dumps(data)


def save_other_video(root, name="otro-video"):
    path = root / name / "stages" / "script"
    path.mkdir(parents=True)
    (path / "script.json").write_text(dumps(rhyme_data()), encoding="utf-8")


@pytest.mark.parametrize(
    ("fmt", "language"), [(f, lang) for f in SAMPLES for lang in ("es", "en")]
)
def test_api_mode_finishes_the_stage_in_all_four_cases(
    tmp_path, monkeypatch, fmt, language
):
    video = make_video(tmp_path, monkeypatch, fmt, language)
    adapter, sdk = adapter_with(dumps(SAMPLES[fmt](language)))
    state = run_script(video, adapter)

    assert state.status == mf.Status.done and state.adapter == "gemini"
    assert state.outputs == ["stages/script/script.json", "stages/script/script.md"]
    saved = json.loads(
        (video / "stages/script/script.json").read_text(encoding="utf-8")
    )
    assert saved["format"] == fmt and saved["language"] == language
    prompt = sdk.models.requests[0]["contents"]
    assert (
        f"Estructura: {saved['variation']['structure']}" in prompt
    )  # lo que se pidió es lo que se registra


def test_default_model_and_env_override(tmp_path, monkeypatch):
    adapter, sdk = adapter_with(dumps(rhyme_data()))
    run_script(make_video(tmp_path, monkeypatch), adapter)
    assert sdk.models.requests[0]["model"] == DEFAULT_MODEL

    monkeypatch.setenv("GEMINI_MODEL", "gemini-otro")
    adapter, sdk = adapter_with(dumps(rhyme_data()))
    run_script(make_video(tmp_path / "b", monkeypatch), adapter)
    assert sdk.models.requests[0]["model"] == "gemini-otro"


def test_similar_script_is_regenerated_until_it_is_different(tmp_path, monkeypatch):
    save_other_video(tmp_path)
    video = make_video(tmp_path, monkeypatch)
    adapter, sdk = adapter_with(
        dumps(rhyme_data()), dumps(rhyme_data()), different_rhyme()
    )
    assert run_script(video, adapter).status == mf.Status.done
    assert len(sdk.models.requests) == 3


def test_still_similar_after_three_attempts_fails_naming_the_video(
    tmp_path, monkeypatch
):
    save_other_video(tmp_path)
    video = make_video(tmp_path, monkeypatch)
    adapter, _ = adapter_with(*[dumps(rhyme_data())] * 3)
    state = run_script(video, adapter)
    assert state.status == mf.Status.failed
    assert "otro-video" in state.error and "similitud" in state.error


def test_a_run_never_makes_more_than_six_calls(tmp_path, monkeypatch):
    save_other_video(tmp_path)
    video = make_video(tmp_path, monkeypatch)
    # Peor caso: en cada intento, una respuesta inválida (reparación) y una válida pero parecida.
    adapter, sdk = adapter_with(*["no es json", dumps(rhyme_data())] * 3)
    state = run_script(video, adapter)
    assert (
        len(sdk.models.requests) == 6
    )  # una 7.ª llamada agotaría el script y fallaría distinto
    assert "otro-video" in state.error


def test_similarity_threshold_can_be_configured(tmp_path, monkeypatch):
    save_other_video(tmp_path)
    monkeypatch.setenv("EVERGREEN_SIMILARITY_THRESHOLD", "1.1")
    adapter, sdk = adapter_with(dumps(rhyme_data()))
    assert (
        run_script(make_video(tmp_path, monkeypatch), adapter).status == mf.Status.done
    )
    assert len(sdk.models.requests) == 1


def test_invalid_threshold_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_SIMILARITY_THRESHOLD", "mucho")
    adapter, _ = adapter_with(dumps(rhyme_data()))
    state = run_script(make_video(tmp_path, monkeypatch), adapter)
    assert (
        state.status == mf.Status.failed
        and "EVERGREEN_SIMILARITY_THRESHOLD" in state.error
    )


def test_two_invalid_replies_fail_keep_raw_and_a_good_rerun_cleans_it(
    tmp_path, monkeypatch
):
    video = make_video(tmp_path, monkeypatch)
    adapter, _ = adapter_with("uno", "dos")
    state = run_script(video, adapter)
    assert state.status == mf.Status.failed
    assert (video / "stages/script/raw.txt").read_text(encoding="utf-8") == "dos"

    adapter, _ = adapter_with(dumps(rhyme_data()))
    assert (
        run_script(video, adapter).status == mf.Status.done
    )  # el siguiente run solo reintenta esta etapa
    assert not (video / "stages/script/raw.txt").exists()


def test_quota_exhausted_fails_with_a_helpful_message(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch)
    adapter, _ = adapter_with(*[api_error(429)] * 4)
    state = run_script(video, adapter)
    assert state.status == mf.Status.failed and "medianoche" in state.error


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"GEMINI_API_KEY": KEY}, "gemini"),
        ({"GEMINI_API_KEY": ""}, "manual"),
        ({"GEMINI_API_KEY": "   "}, "manual"),
        ({"GEMINI_API_KEY": KEY, "EVERGREEN_SCRIPT_MODE": "manual"}, "manual"),
        ({"GEMINI_API_KEY": KEY, "EVERGREEN_SCRIPT_MODE": " Manual "}, "manual"),
        ({"GEMINI_API_KEY": KEY, "EVERGREEN_SCRIPT_MODE": "api"}, "gemini"),
    ],
)
def test_mode_selection(monkeypatch, env, expected):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert ScriptAdapter().name == expected


def test_manual_mode_never_builds_a_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_SCRIPT_MODE", "manual")

    def no_client(*a):
        raise AssertionError("no debía crear cliente")

    video = make_video(tmp_path, monkeypatch)
    state = run_script(video, ScriptAdapter(client_factory=no_client))
    assert state.status == mf.Status.awaiting_manual and state.adapter == "manual"
    assert (video / "stages/script/MANUAL.md").is_file()


def test_generation_json_records_model_and_calls(tmp_path, monkeypatch):
    video = make_video(tmp_path, monkeypatch)
    adapter, _ = adapter_with(api_error(503), dumps(rhyme_data()))
    run_script(video, adapter)
    gen = json.loads((video / "stages/script/generation.json").read_text("utf-8"))
    assert gen == {"model": DEFAULT_MODEL, "attempt": 1, "calls": 2}
