"""Etapa `voice`: elige el modo según EVERGREEN_VOICE_MODE (`piper` o `manual`; `gemini` si hay clave)."""

import os

from evergreen import registry
from evergreen.adapters.base import StageContext, StageResult
from evergreen.adapters.manual import ManualAdapter
from evergreen.errors import EvergreenError
from evergreen.voice_audio.gemini_voice import GeminiVoiceAdapter
from evergreen.voice_audio.piper import PiperAdapter

MODES = ("manual", "piper", "gemini")


class VoiceAdapter:
    def __init__(
        self,
        piper: PiperAdapter | None = None,
        gemini: GeminiVoiceAdapter | None = None,
    ) -> None:
        self._piper = piper or PiperAdapter()
        self._gemini = gemini or GeminiVoiceAdapter()

    @staticmethod
    def _mode() -> str:
        explicit = os.environ.get("EVERGREEN_VOICE_MODE", "").strip().lower()
        if explicit:
            return explicit
        return "gemini" if os.environ.get("GEMINI_API_KEY", "").strip() else "manual"

    @property
    def name(self) -> str:
        return self._mode()

    def run(self, ctx: StageContext) -> StageResult:
        mode = self._mode()
        if mode not in MODES:
            raise EvergreenError(
                f"EVERGREEN_VOICE_MODE='{mode}' no es válido. Usa: {', '.join(MODES)}."
            )
        if mode == "piper":
            return self._piper.run(ctx)
        if mode == "gemini":
            if not os.environ.get("GEMINI_API_KEY", "").strip():
                raise EvergreenError(
                    "EVERGREEN_VOICE_MODE=gemini necesita GEMINI_API_KEY en .env."
                )
            return self._gemini.run(ctx)
        return ManualAdapter(registry.MANUAL_FILES["voice"]).run(ctx)
