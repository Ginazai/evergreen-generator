"""Cliente delgado de Gemini (SDK oficial `google-genai`).

El SDK se importa solo aquí: cargarlo cuesta ~0,5 s y el resto del CLI no lo necesita.
"""

import time
from collections.abc import Callable

from google import genai
from google.genai import errors, types

from evergreen.errors import EvergreenError
from evergreen.script_writer.models import LongScript, RhymeScript, parse_script

MAX_CALLS = 6  # tope por ejecución de la etapa, reintentos incluidos
RETRY_DELAYS = (2, 4, 8)  # espera creciente en segundos: hasta 3 reintentos
RETRYABLE = {429, 503}  # límite de uso y servicio saturado
TIMEOUT_MS = 120_000

# Propiedades de JSON Schema que Gemini documenta como admitidas en `response_json_schema`.
_ALLOWED = {
    "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description", "enum",
    "items", "prefixItems", "minItems", "maxItems", "minimum", "maximum", "anyOf", "oneOf",
    "properties", "additionalProperties", "required", "propertyOrdering",
}  # fmt: skip
_NAME_MAPS = {
    "properties",
    "$defs",
}  # sus claves son nombres de campo, no palabras del esquema


class InvalidResponse(EvergreenError):
    """La respuesta del modelo no cumple el contrato, ni tras la reparación."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def to_gemini_schema(model: type[RhymeScript] | type[LongScript]) -> dict:
    """Esquema de Pydantic reducido a lo que Gemini admite. Lo que se pierde (longitudes mínimas,
    patrones) lo vuelve a comprobar `parse_script`."""

    def clean(node):
        if isinstance(node, list):
            return [clean(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:  # junto a $ref solo se admiten claves que empiecen por $
            return {"$ref": node["$ref"]}
        if "const" in node:
            node = {**node, "enum": [node["const"]]}
        out = {}
        for key, value in node.items():
            if key not in _ALLOWED:
                continue
            if key in _NAME_MAPS:
                out[key] = {name: clean(sub) for name, sub in value.items()}
            else:
                out[key] = clean(value)
        return out

    return clean(model.model_json_schema())


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        sdk=None,
        sleep: Callable[[float], None] = time.sleep,
        max_calls: int = MAX_CALLS,
    ) -> None:
        self._key = api_key
        self.model = model
        self.calls = 0
        self._max_calls = max_calls
        self._sleep = sleep
        # attempts=1 desactiva los reintentos internos del SDK: aquí se cuentan contra el tope.
        self._sdk = sdk or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )

    def generate(self, prompt: str, schema: dict) -> str:
        """Devuelve el texto de la respuesta. Reintenta ante límite de uso; el resto de errores sube."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json", response_json_schema=schema
        )
        delays = iter(RETRY_DELAYS)
        while True:
            if self.calls >= self._max_calls:
                raise EvergreenError(
                    f"Se alcanzó el tope de {self._max_calls} llamadas a Gemini para esta etapa. "
                    "Vuelve a ejecutar `evergreen run` más tarde."
                )
            self.calls += 1
            try:
                response = self._sdk.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except errors.APIError as e:
                delay = next(delays, None)
                if e.code in RETRYABLE and delay is not None:
                    self._sleep(delay)
                    continue
                raise self._explain(e) from e
            return self._text(response)

    def _text(self, response) -> str:
        text = response.text
        if text:
            return text
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(getattr(feedback, "block_reason", None), "name", None)
        if reason is None and response.candidates:
            finish = response.candidates[0].finish_reason
            reason = getattr(finish, "name", None)
        raise EvergreenError(
            f"Gemini no devolvió texto (motivo: {reason or 'desconocido'})."
        )

    def _explain(self, e: errors.APIError) -> EvergreenError:
        detail = (e.message or "").replace(self._key, "***")
        if e.code == 429:
            return EvergreenError(
                "Gemini rechazó la solicitud por límite de uso (cuota por minuto o por día). "
                "La cuota diaria se reinicia a medianoche (hora del Pacífico). Vuelve a ejecutar "
                "`evergreen run` más tarde o usa el modo manual (EVERGREEN_SCRIPT_MODE=manual)."
            )
        if e.code in (401, 403):
            return EvergreenError(
                f"Gemini no aceptó la clave GEMINI_API_KEY ({e.code}). Revísala en Google AI Studio."
            )
        return EvergreenError(f"Error de Gemini ({e.code} {e.status}): {detail}")


def generate_script(client: GeminiClient, prompt: str, fmt: str, language):
    """Genera y valida un guion; si no valida, un único intento de reparación."""
    schema = to_gemini_schema(RhymeScript if fmt == "rhyme" else LongScript)
    text = client.generate(prompt, schema)
    try:
        return parse_script(text, fmt, language)
    except EvergreenError as first:
        repair = (
            f"{prompt}\n\nTu respuesta anterior no cumplió el formato:\n{first}\n\n"
            f"Respuesta anterior:\n{text}\n\n"
            "Corrígela y responde SOLO con el JSON completo."
        )
        text = client.generate(repair, schema)
        try:
            return parse_script(text, fmt, language)
        except EvergreenError as second:
            raise InvalidResponse(str(second), raw=text) from second
