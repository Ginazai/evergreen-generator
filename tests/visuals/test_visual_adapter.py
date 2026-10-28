import json

import pytest
from script_samples import long_data, rhyme_data
from test_images import jpeg

from evergreen import manifest as mf
from evergreen import project, runner
from evergreen.errors import EvergreenError
from evergreen.visuals.adapter import CloudflareImageAdapter, ImageAdapter
from evergreen.visuals.cloudflare import QuotaExceeded

IMG = jpeg(1280, 720)


class FakeClient:
    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def generate(self, prompt, size, refs=()):
        self.calls.append((prompt, size, list(refs)))
        item = self.script.pop(0) if self.script else IMG
        if isinstance(item, Exception):
            raise item
        return item


def adapter(*script, shrink=lambda p: b"REF:" + p.name.encode()):
    fake = FakeClient(*script)
    return CloudflareImageAdapter(lambda a, t: fake, shrink), fake


def video(tmp_path, fmt, data, done, aspect=None):
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


def run(v, stage, a):
    return runner.run(v, {stage: a}).stages[stage]


def put_sheets(v):
    d = v / "stages/characters"
    d.mkdir(parents=True, exist_ok=True)
    for cid in ("lola", "pipo"):
        (d / f"personaje-{cid}.jpg").write_bytes(IMG)


def test_scenes_use_character_sheets_as_references_in_order(tmp_path):
    v = video(tmp_path, "long", long_data(), ("script", "voice", "music", "characters"))
    put_sheets(v)
    a, fake = adapter()
    state = run(v, "scenes", a)
    assert state.status == mf.Status.done and len(fake.calls) == 8
    prompt, size, refs = fake.calls[0]
    assert size == (1280, 720)
    assert refs == [b"REF:personaje-lola.jpg"]  # solo Lola habla en la 1.ª toma
    assert "Lola looks exactly like reference image 0" in prompt
    entries = json.loads((v / "stages/scenes/images.json").read_text("utf-8"))
    assert len(entries) == 8 and entries[0]["image"] == "escena-1-1.jpg"
    assert all(o.startswith("stages/scenes/") for o in state.outputs)


def test_missing_sheet_means_no_references_and_no_reference_sentence(tmp_path):
    v = video(tmp_path, "long", long_data(), ("script", "voice", "music", "characters"))
    a, fake = adapter()
    run(v, "scenes", a)
    prompt, _, refs = fake.calls[0]
    assert refs == [] and "reference image" not in prompt


def test_rhyme_makes_sheets_first_then_uses_them_and_is_vertical(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data(), ("script", "song"))
    a, fake = adapter()
    state = run(v, "visuals", a)
    assert state.status == mf.Status.done
    (sheet_prompt, sheet_size, sheet_refs), (_shot_prompt, shot_size, shot_refs) = (
        fake.calls
    )
    assert (
        "Character design sheet" in sheet_prompt
        and sheet_size == (768, 768)
        and not sheet_refs
    )
    assert shot_size == (720, 1280) and shot_refs == [b"REF:personaje-lola.jpg"]
    keys = [
        e["key"]
        for e in json.loads((v / "stages/visuals/images.json").read_text("utf-8"))
    ]
    assert keys == ["personaje-lola", "toma-1"]


def test_aspect_override_changes_the_size(tmp_path):
    v = video(
        tmp_path,
        "long",
        long_data(),
        ("script", "voice", "music", "characters"),
        aspect="9:16",
    )
    a, fake = adapter()
    run(v, "scenes", a)
    assert fake.calls[0][1] == (720, 1280)


def test_quota_mid_run_keeps_done_images_and_resume_skips_them(tmp_path):
    v = video(tmp_path, "long", long_data(), ("script", "voice", "music", "characters"))
    a, _fake = adapter(IMG, IMG, QuotaExceeded("Cuota agotada."))
    state = run(v, "scenes", a)
    assert state.status == mf.Status.failed
    assert (
        "Se generaron 2 de 8" in state.error
        and "EVERGREEN_IMAGE_MODE=manual" in state.error
    )
    b, fake2 = adapter()
    assert run(v, "scenes", b).status == mf.Status.done
    assert len(fake2.calls) == 6


def test_images_already_in_inbox_are_not_regenerated(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data(), ("script", "song"))
    inbox = v / "stages/visuals/inbox"
    inbox.mkdir(parents=True)
    (inbox / "personaje-lola.png").write_bytes(b"png")
    a, fake = adapter()
    run(v, "visuals", a)
    assert len(fake.calls) == 1 and "Character design sheet" not in fake.calls[0][0]
    assert fake.calls[0][2] == [b"REF:personaje-lola.png"]


def test_non_image_response_and_failed_shrink_are_clear_errors(tmp_path):
    v = video(tmp_path, "rhyme", rhyme_data(), ("script", "song"))
    a, _ = adapter(b"esto no es una imagen")
    state = run(v, "visuals", a)
    assert state.status == mf.Status.failed and "no es una imagen" in state.error
    assert not list((v / "stages/visuals").glob("*.part"))

    def broken(p):
        raise RuntimeError("sin ffmpeg")

    w = video(tmp_path / "otro", "rhyme", rhyme_data(), ("script", "song"))
    (w / "stages/visuals").mkdir(exist_ok=True)
    (w / "stages/visuals/personaje-lola.jpg").write_bytes(IMG)
    b, _ = adapter(shrink=broken)
    assert "sin ffmpeg" in run(w, "visuals", b).error


def test_missing_script_fails_clearly(tmp_path):
    v = project.create("X", mf.Format.rhyme, mf.Language.es, tmp_path)
    (v / "stages/script").mkdir(exist_ok=True)
    m = mf.load(v / "manifest.yaml")
    m.stages["script"].status = mf.Status.done
    m.stages["song"].status = mf.Status.done
    mf.save(m, v / "manifest.yaml")
    a, _ = adapter()
    assert "etapa `script`" in run(v, "visuals", a).error


def test_dispatcher_modes(tmp_path, monkeypatch):
    v = video(tmp_path, "rhyme", rhyme_data(), ("script", "song"))
    cf, _fake = adapter()
    d = ImageAdapter(cf)
    assert (
        d.name == "manual" and run(v, "visuals", d).status == mf.Status.awaiting_manual
    )

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    assert d.name == "cloudflare" and run(v, "visuals", d).status == mf.Status.done

    monkeypatch.setenv("EVERGREEN_IMAGE_MODE", "manual")
    assert d.name == "manual"
    monkeypatch.setenv("EVERGREEN_IMAGE_MODE", "nada")
    assert (
        "EVERGREEN_IMAGE_MODE"
        in run(
            video(tmp_path / "x", "rhyme", rhyme_data(), ("script", "song")),
            "visuals",
            d,
        ).error
    )
    monkeypatch.setenv("EVERGREEN_IMAGE_MODE", "cloudflare")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    assert (
        "CLOUDFLARE_API_TOKEN"
        in run(
            video(tmp_path / "y", "rhyme", rhyme_data(), ("script", "song")),
            "visuals",
            d,
        ).error
    )


def test_plan_error_for_mismatched_stage_is_reported(tmp_path):
    from evergreen.adapters.base import StageContext

    v = video(tmp_path, "rhyme", rhyme_data(), ("script",))
    ctx = StageContext("scenes", v / "stages/script", v, mf.load(v / "manifest.yaml"))
    with pytest.raises(EvergreenError, match="no aplica"):
        CloudflareImageAdapter(lambda a, t: FakeClient()).run(ctx)


def test_images_that_never_show_up_are_reported(tmp_path, monkeypatch):
    v = video(tmp_path, "rhyme", rhyme_data(), ("script", "song"))
    a, _ = adapter()
    monkeypatch.setattr(
        CloudflareImageAdapter, "_save", staticmethod(lambda *args: None)
    )
    assert "Faltan imágenes" in run(v, "visuals", a).error
