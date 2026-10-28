"""Voz local con Piper: sin cuota ni internet (salvo la primera descarga de la voz)."""

import os
import wave
from collections.abc import Callable
from pathlib import Path

from evergreen import fsutil
from evergreen.adapters.base import Done, StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script
from evergreen.voice_audio.timeline import is_valid_wav, wav_seconds, write_timeline

# Nombres de rhasspy/piper-voices. Solo en_US-lessac-medium sale en la documentación leída;
# es_ES-davefx-medium no se verificó: si no existe, define PIPER_VOICE.
DEFAULT_VOICES = {"es": "es_ES-davefx-medium", "en": "en_US-lessac-medium"}
PAUSE_SECONDS = 0.35


def load_voice(language: str, voices_dir: Path):
    """Descarga la voz si falta y la carga. Import tardío: piper es una dependencia opcional."""
    try:
        from piper import PiperVoice
        from piper.download_voices import download_voice
    except ImportError as e:
        raise EvergreenError(
            "Falta piper-tts. Reconstruye la imagen (`docker compose build`) o instala `.[piper]`."
        ) from e
    name = os.environ.get("PIPER_VOICE", "").strip() or DEFAULT_VOICES[language]
    model = voices_dir / f"{name}.onnx"
    if not model.is_file():
        voices_dir.mkdir(parents=True, exist_ok=True)
        download_voice(name, voices_dir)
    return PiperVoice.load(model)


class PiperAdapter:
    """Etapa `voice` con Piper. Un WAV por escena; reanuda saltando las ya hechas."""

    name = "piper"

    def __init__(self, loader: Callable | None = None) -> None:
        self._loader = loader or load_voice

    def run(self, ctx: StageContext) -> StageResult:
        script_path = ctx.video_dir / "stages" / "script" / "script.json"
        if not script_path.is_file():
            raise EvergreenError(
                "No encuentro el guion: ejecuta primero la etapa `script`."
            )
        script = read_script(script_path)
        voice = None  # se carga solo si hay escenas por hacer
        outputs, entries = [], []
        for scene in script.body.scenes:
            path = ctx.stage_dir / f"{scene.id}.wav"
            if not is_valid_wav(path):
                voice = voice or self._loader(
                    script.language.value, ctx.video_dir.parent / "_piper"
                )
                self._synthesize(voice, [b.text for b in scene.beats], path)
            outputs.append(path)
            entries.append(
                {"scene_id": scene.id, "file": path.name, "seconds": wav_seconds(path)}
            )
        return Done([*outputs, write_timeline(ctx.stage_dir, entries)])

    @staticmethod
    def _synthesize(voice, texts: list[str], path: Path) -> None:
        # shortcut: todos los personajes y el narrador usan la misma voz; separar voces
        # exige un modelo por personaje, se añade si Piper resulta aceptable.
        part = path.with_suffix(".part")
        with wave.open(str(part), "wb") as wav:
            for i, text in enumerate(texts):
                if i:
                    wav.writeframes(
                        b"\x00\x00" * int(voice.config.sample_rate * PAUSE_SECONDS)
                    )
                voice.synthesize_wav(text, wav, set_wav_format=(i == 0))
        fsutil.replace(part, path)
