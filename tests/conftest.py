import pytest
from fakes import Fake
from google import genai

from evergreen import manifest as mf
from evergreen import project, registry


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERGREEN_PROJECTS_DIR", str(tmp_path))
    folder = project.create("Patitos", mf.Format.rhyme, mf.Language.es, tmp_path)
    # Sin puertas de aprobación: las pruebas del ejecutor corren de principio a fin.
    m = mf.load(folder / "manifest.yaml")
    m.review_gates = []
    mf.save(m, folder / "manifest.yaml")
    return folder


@pytest.fixture
def adapters(monkeypatch):
    """Un Fake por etapa del formato rhyme, registrado como adaptador."""
    fakes = {name: Fake() for name in registry.STAGES["rhyme"]}
    monkeypatch.setattr(registry, "ADAPTERS", fakes)
    return fakes


GEMINI_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "EVERGREEN_SCRIPT_MODE",
    "EVERGREEN_SIMILARITY_THRESHOLD",
    "EVERGREEN_VOICE_MODE",
    "GEMINI_TTS_MODEL",
    "PIPER_VOICE",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "EVERGREEN_IMAGE_MODE",
)


@pytest.fixture(autouse=True)
def _never_reach_the_real_gemini(monkeypatch):
    """En Docker el .env pasa la clave real al contenedor: ninguna prueba debe usarla."""
    for var in GEMINI_VARS:
        monkeypatch.delenv(var, raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("Una prueba intentó crear un cliente real de Gemini.")

    monkeypatch.setattr(genai, "Client", boom)


@pytest.fixture(autouse=True)
def _never_reach_the_real_cloudflare(monkeypatch):
    from evergreen.visuals import cloudflare

    def boom(*args, **kwargs):
        raise AssertionError("Una prueba intentó llamar a la red real de Cloudflare.")

    # `post` toma `_http_post` como valor por defecto al importar: se corta una capa más abajo.
    monkeypatch.setattr(cloudflare.urllib.request, "urlopen", boom)
