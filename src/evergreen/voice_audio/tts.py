"""Cliente delgado de Gemini TTS (API Interactions). Una petición = una unidad de cuota diaria."""

import base64
import time
from collections.abc import Callable

import httpx
from google import genai
from google.genai import errors, types

from evergreen.errors import EvergreenError
from evergreen.voice_audio.requests import VoiceRequest

MAX_CALLS = (
    12  # tope por ejecución, reintentos incluidos (la cuota gratuita es 10 al día)
)
RETRY_DELAYS = (25, 50)  # el límite por minuto es 3: hay que esperar a que se libere
PACE_SECONDS = 21  # separación mínima entre peticiones para no pasar de 3 por minuto
RETRYABLE = {429, 503}
TIMEOUT_MS = 120_000


class QuotaExceeded(EvergreenError):
    """La cuota se agotó (diaria, o por minuto tras agotar los reintentos)."""


class TtsClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        sdk=None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_calls: int = MAX_CALLS,
    ) -> None:
        self._key = api_key
        self.model = model
        self.calls = 0
        self._max_calls = max_calls
        self._sleep, self._clock = sleep, clock
        self._last: float | None = None
        self._sdk = sdk or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    @staticmethod
    def body(request: VoiceRequest, voices: dict[str, str]) -> dict:
        turns = [
            {
                "type": "text",
                "text": t.text,
                "annotations": [
                    {
                        "type": "speech_metadata",
                        "speaker": t.speaker,
                        "style": t.emotion,
                    }
                ],
            }
            for t in request.turns
        ]
        speakers = request.speakers
        if len(speakers) == 1:
            config = [{"voice": voices[speakers[0]]}]
        else:
            config = {
                "speakers": [{"speaker": s, "voice": voices[s]} for s in speakers]
            }
        return {
            "model": None,  # se completa al llamar
            "input": [{"type": "user_input", "content": turns}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": config},
        }

    def speak(self, request: VoiceRequest, voices: dict[str, str]) -> bytes:
        """Devuelve el WAV de la petición. Reintenta límites por minuto; la cuota diaria no."""
        body = {**self.body(request, voices), "model": self.model}
        delays = iter(RETRY_DELAYS)
        while True:
            if self.calls >= self._max_calls:
                raise QuotaExceeded(
                    f"Se alcanzó el tope de {self._max_calls} llamadas de voz para esta ejecución."
                )
            self._pace()
            self.calls += 1
            try:
                interaction = self._sdk.interactions.create(**body)
            except httpx.TimeoutException as e:
                raise EvergreenError(
                    f"Gemini no respondió en {TIMEOUT_MS // 1000} s para `{request.key}`. Suele ser el límite "
                    "de uso diario (la API deja de contestar) o un corte de red. Prueba más tarde o usa "
                    "EVERGREEN_VOICE_MODE=piper."
                ) from e
            except errors.APIError as e:
                self._last = self._clock()
                delay = next(delays, None)
                if e.code in RETRYABLE and delay is not None and not self._daily(e):
                    print(
                        f"  Gemini {e.code}: reintento en {delay} s ({(e.message or '')[:160]})",
                        flush=True,
                    )
                    self._sleep(delay)
                    continue
                raise self._explain(e) from e
            self._last = self._clock()
            return self._audio(interaction)

    def _pace(self) -> None:
        if self._last is not None:
            wait = PACE_SECONDS - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)

    @staticmethod
    def _daily(e: errors.APIError) -> bool:
        # shortcut: se adivina por el texto del error (no está documentado); si la API cambia
        # el mensaje, se reintenta de más y el tope de llamadas lo detiene.
        text = (e.message or "").lower()
        return "perday" in text or "per day" in text or "daily" in text

    def _audio(self, interaction) -> bytes:
        audio = getattr(interaction, "output_audio", None)
        data = getattr(audio, "data", None)
        if not data:
            raise EvergreenError("Gemini no devolvió audio para esta petición.")
        return base64.b64decode(data)

    def _explain(self, e: errors.APIError) -> EvergreenError:
        detail = (e.message or "").replace(self._key, "***")
        if e.code == 429:
            return QuotaExceeded(
                "Gemini rechazó la solicitud de voz por límite de uso (cuota por minuto o por día). "
                "La cuota diaria se reinicia a medianoche (hora del Pacífico). "
                f"Respuesta de Gemini: {detail[:300]}"
            )
        if e.code in (401, 403):
            return EvergreenError(
                f"Gemini no aceptó la clave GEMINI_API_KEY ({e.code}). Revísala en Google AI Studio."
            )
        return EvergreenError(f"Error de Gemini TTS ({e.code} {e.status}): {detail}")
