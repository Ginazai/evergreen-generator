"""Etapa `voice` con Gemini TTS: un WAV por petición (escena o parte de escena), reanudable."""

import os
from collections.abc import Callable
from pathlib import Path

from evergreen import fsutil
from evergreen.adapters.base import Done, StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script
from evergreen.voice_audio.requests import plan_requests
from evergreen.voice_audio.timeline import is_valid_wav, wav_seconds, write_timeline
from evergreen.voice_audio.tts import QuotaExceeded, TtsClient
from evergreen.voice_audio.voices import assign, load_voices

DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"


class GeminiVoiceAdapter:
    name = "gemini"

    def __init__(self, client_factory: Callable[[str, str], TtsClient] | None = None):
        self._factory = client_factory or TtsClient

    def run(self, ctx: StageContext) -> StageResult:
        script_path = ctx.video_dir / "stages" / "script" / "script.json"
        if not script_path.is_file():
            raise EvergreenError(
                "No encuentro el guion: ejecuta primero la etapa `script`."
            )
        script = read_script(script_path)
        voices = assign(
            [c.id for c in script.characters], load_voices(ctx.video_dir.parent)
        )
        requests = plan_requests(script.body.scenes)
        pending = [
            r for r in requests if not is_valid_wav(ctx.stage_dir / f"{r.key}.wav")
        ]

        if pending:
            model = os.environ.get("GEMINI_TTS_MODEL", "").strip() or DEFAULT_TTS_MODEL
            client = self._factory(os.environ.get("GEMINI_API_KEY", "").strip(), model)
            for done, request in enumerate(pending):
                print(f"Voz {done + 1}/{len(pending)}: {request.key}…", flush=True)
                try:
                    audio = client.speak(request, voices)
                except QuotaExceeded as e:
                    raise EvergreenError(
                        f"{e} Se generaron {len(requests) - len(pending) + done} de "
                        f"{len(requests)} audios; al volver a ejecutar `evergreen run` se retoma "
                        f"desde `{request.key}`."
                    ) from e
                self._save(ctx.stage_dir / f"{request.key}.wav", audio)

        paths = [ctx.stage_dir / f"{r.key}.wav" for r in requests]
        entries = [
            {"scene_id": r.scene_id, "file": p.name, "seconds": wav_seconds(p)}
            for r, p in zip(requests, paths, strict=True)
        ]
        return Done([*paths, write_timeline(ctx.stage_dir, entries)])

    @staticmethod
    def _save(path: Path, audio: bytes) -> None:
        part = path.with_suffix(".part")
        part.write_bytes(audio)
        if not is_valid_wav(part):
            part.unlink()
            raise EvergreenError("Gemini devolvió audio que no es un WAV válido.")
        fsutil.replace(part, path)
