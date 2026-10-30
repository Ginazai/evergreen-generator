import json
import time
from pathlib import Path

from script_samples import long_data
from streamlit.testing.v1 import AppTest

from evergreen import jobs, project
from evergreen import manifest as mf

APP = str(Path(__file__).resolve().parents[2] / "src/evergreen/gui/app.py")


def at(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    return AppTest.from_file(APP, default_timeout=30).run()


def long_video(tmp_path):
    v = project.create("Los patitos", mf.Format.long, mf.Language.es, tmp_path)
    m = mf.load(v / "manifest.yaml")
    for st in m.stages.values():
        st.status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    (v / "stages/script/script.json").write_text(
        json.dumps(long_data()), encoding="utf-8"
    )
    return v


def button(app, label):
    return next(b for b in app.button if label in b.label)


def test_first_run_invites_to_create_a_video_and_creates_it(tmp_path, monkeypatch):
    app = at(tmp_path, monkeypatch)
    assert app.info[0].value.startswith("Crea tu primer video")
    app.sidebar.text_input[0].set_value("Mis patitos")
    app.sidebar.get("form_submit_button")[0].click()
    app.run()
    assert [v.title for v in project.list_videos(tmp_path)] == ["Mis patitos"]
    assert app.title[0].value == "Mis patitos" and not app.exception


def test_empty_title_shows_the_core_error(tmp_path, monkeypatch):
    app = at(tmp_path, monkeypatch)
    app.sidebar.get("form_submit_button")[0].click()
    app.run()
    assert "título" in app.error[0].value


def test_stage_panels_actions_and_stale_banner(tmp_path, monkeypatch):
    long_video(tmp_path)
    app = at(tmp_path, monkeypatch)
    assert not app.exception and len(app.expander) >= 6
    button(app, "Rehacer").click()  # primera etapa: script
    app.run()
    assert "script" in {
        n
        for n, s in mf.load(next(tmp_path.glob("*/manifest.yaml"))).stages.items()
        if s.status == mf.Status.pending
    }
    assert "Desactualizadas" in app.warning[0].value


def test_script_edit_through_the_form_marks_stale(tmp_path, monkeypatch):
    v = long_video(tmp_path)
    app = at(tmp_path, monkeypatch)
    title = next(t for t in app.text_input if t.label == "Título del guion")
    title.set_value("Nuevo título")
    button(app, "Guardar guion").click()
    app.run()
    assert (
        json.loads((v / "stages/script/script.json").read_text())["title"]
        == "Nuevo título"
    )
    assert "Guardado" in app.success[0].value


def test_invalid_raw_json_is_rejected_without_saving(tmp_path, monkeypatch):
    v = long_video(tmp_path)
    before = (v / "stages/script/script.json").read_text()
    app = at(tmp_path, monkeypatch)
    next(t for t in app.text_area if t.label == "script.json").set_value("{roto")
    app.checkbox[0].check()
    button(app, "Guardar guion").click()
    app.run()
    assert app.error and (v / "stages/script/script.json").read_text() == before


def test_config_page_validates_and_saves(tmp_path, monkeypatch):
    app = at(tmp_path, monkeypatch)
    app.sidebar.radio[0].set_value("Elenco, voces y estilo").run()
    next(t for t in app.text_area if t.label == "style.yaml").set_value(
        "style: acuarela\n"
    )
    button(app, "Guardar style.yaml").click()
    app.run()
    assert (tmp_path / "style.yaml").read_text() == "style: acuarela\n"
    next(t for t in app.text_area if t.label == "voices.yaml").set_value(
        "narrador: x\n"
    )
    button(app, "Guardar voices.yaml").click()
    app.run()
    assert "voices.yaml no es válido" in app.error[0].value


def test_settings_page_saves_without_leaking_the_key(tmp_path, monkeypatch):
    app = at(tmp_path, monkeypatch)
    app.sidebar.radio[0].set_value("Ajustes").run()
    next(t for t in app.text_input if t.label == "GEMINI_API_KEY").set_value(
        "AIzaSecreta1234"
    )
    app.get("form_submit_button")[0].click()
    app.run()
    assert config_read(tmp_path) == "AIzaSecreta1234"
    app = at(tmp_path, monkeypatch)  # sesión nueva: la clave no vuelve a pantalla
    app.sidebar.radio[0].set_value("Ajustes").run()
    shown = next(t for t in app.text_input if t.label == "GEMINI_API_KEY")
    assert shown.value == "" and shown.placeholder == "••••1234"


def config_read(tmp_path):
    from evergreen import config

    return config.read_settings()["GEMINI_API_KEY"]


def test_run_button_starts_background_job(tmp_path, monkeypatch):
    v = project.create("Rima", mf.Format.rhyme, mf.Language.es, tmp_path)
    app = at(tmp_path, monkeypatch)
    button(app, "Ejecutar").click()
    app.run()
    assert not app.exception
    end = time.time() + 60
    while jobs.is_running(v) and time.time() < end:
        time.sleep(0.1)
    assert "script:" in jobs.read_log(v)


def voice_under_review(tmp_path, monkeypatch, keys):
    """Video largo con la voz lista pero sin aprobar (así queda tras `run`, por la puerta de revisión)."""
    v = long_video(tmp_path)
    m = mf.load(v / "manifest.yaml")
    m.stages["voice"].status = mf.Status.awaiting_approval
    mf.save(m, v / "manifest.yaml")
    d = v / "stages/voice"
    for k in keys:
        (d / f"{k}.wav").write_bytes(b"x")
    (d / "timeline.json").write_text(
        json.dumps([{"scene_id": k, "file": f"{k}.wav"} for k in keys]),
        encoding="utf-8",
    )
    started = []
    monkeypatch.setattr(jobs, "start", started.append)  # sin lanzar un proceso real
    return v, d, started


def test_regenerate_some_items_while_the_stage_awaits_approval(tmp_path, monkeypatch):
    v, d, started = voice_under_review(
        tmp_path, monkeypatch, ["escena-1", "escena-2", "escena-3"]
    )
    app = at(tmp_path, monkeypatch)
    app.multiselect(key="sel-voice").set_value(["escena-1", "escena-3"]).run()
    button(app, "Regenerar 2 y ejecutar").click()
    app.run()
    assert not app.exception and not app.error
    assert not (d / "escena-1.wav").exists() and not (d / "escena-3.wav").exists()
    assert (d / "escena-2.wav").exists()  # la buena no se toca
    assert mf.load(v / "manifest.yaml").stages["voice"].status == mf.Status.pending
    assert started == [v]  # y se retoma la etapa sin otro clic


def test_nothing_selected_offers_no_action_and_does_not_touch_files(
    tmp_path, monkeypatch
):
    _, d, started = voice_under_review(tmp_path, monkeypatch, ["escena-1"])
    app = at(tmp_path, monkeypatch)
    assert not [b for b in app.button if "Regenerar" in b.label]
    assert (d / "escena-1.wav").exists() and not started


def test_theme_tokens_are_resolved_by_the_browser_not_the_server():
    """Regresión: Streamlit no avisa al servidor al cambiar de tema, así que --accent y --surface
    calculados con st.context.theme se quedaban en el tema anterior."""
    css = Path(APP).with_name("style.css").read_text(encoding="utf-8")
    assert "--surface: light-dark(" in css and "--accent: light-dark(" in css
    assert "context.theme" not in Path(APP).read_text(encoding="utf-8")
