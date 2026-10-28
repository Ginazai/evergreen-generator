from pathlib import Path

from typer.testing import CliRunner

from evergreen.cli import app

runner = CliRunner()
SECRETS = {"GEMINI_API_KEY": "fake-key-123", "ELEVENLABS_API_KEY": "fake-key-456"}


def leaks(root: Path, outputs: list[str]) -> list[str]:
    """Dónde aparece algún secreto: en el contenido de archivos, en sus nombres o en la salida del CLI."""
    found = []
    texts = [("<salida CLI>", o) for o in outputs]
    texts += [
        (str(p), p.name + p.read_text(encoding="utf-8"))
        for p in root.rglob("*")
        if p.is_file()
    ]
    for where, text in texts:
        found += [f"{where}: {v}" for v in SECRETS.values() if v in text]
    return found


def test_keys_never_reach_files_or_output(video, adapters, monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    outputs = [
        runner.invoke(app, ["run", video.name]).output,
        runner.invoke(app, ["status", video.name]).output,
        runner.invoke(app, ["list"]).output,
    ]
    assert leaks(video.parent, outputs) == []


def test_scanner_detects_a_planted_key(video):
    (video / "stages" / "script" / "nota.txt").write_text(
        "x fake-key-123 y", encoding="utf-8"
    )
    assert leaks(video.parent, []) != []


def test_key_never_reaches_files_or_manifest_in_api_mode(tmp_path, monkeypatch):
    """El camino API con un SDK ficticio, también cuando el error de Gemini cita la clave."""
    import json

    from gemini_fakes import FakeSDK, api_error
    from script_samples import rhyme_data

    from evergreen import manifest as mf
    from evergreen import project, runner
    from evergreen.script_writer.adapter import ScriptAdapter
    from evergreen.script_writer.gemini import GeminiClient

    monkeypatch.setenv("GEMINI_API_KEY", SECRETS["GEMINI_API_KEY"])
    video = project.create("Patitos", mf.Format.rhyme, mf.Language.es, tmp_path)

    def run(*script):
        sdk = FakeSDK(*script)
        adapter = ScriptAdapter(
            lambda k, m: GeminiClient(k, m, sdk=sdk, sleep=lambda s: None)
        )
        return runner.run(video, {"script": adapter})

    failed = run(api_error(400, message=f"clave {SECRETS['GEMINI_API_KEY']} inválida"))
    assert failed.stages["script"].status == mf.Status.failed
    run(json.dumps(rhyme_data()))
    assert leaks(tmp_path, [str(failed)]) == []
