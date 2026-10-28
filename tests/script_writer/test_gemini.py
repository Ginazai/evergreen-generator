import json

import pytest
from gemini_fakes import FakeSDK, api_error, response
from script_samples import long_data, rhyme_data

from evergreen.errors import EvergreenError
from evergreen.manifest import Language
from evergreen.script_writer.gemini import (
    _ALLOWED,
    GeminiClient,
    InvalidResponse,
    generate_script,
    to_gemini_schema,
)
from evergreen.script_writer.models import LongScript, RhymeScript

KEY = "fake-key-123"
GOOD = json.dumps(rhyme_data(), ensure_ascii=False)
SCHEMA = {"type": "object"}


def client(*script, **kw):
    sleeps = []
    sdk = FakeSDK(*script)
    c = GeminiClient(KEY, "gemini-test", sdk=sdk, sleep=sleeps.append, **kw)
    return c, sdk, sleeps


# --- esquema ---------------------------------------------------------------------------------


def walk(node, path="$"):
    """Todas las palabras de esquema usadas deben estar en la lista que Gemini admite."""
    if isinstance(node, list):
        for i, x in enumerate(node):
            yield from walk(x, f"{path}[{i}]")
    elif isinstance(node, dict):
        for key, value in node.items():
            if path.endswith(("properties", "$defs")):  # claves = nombres de campo
                yield from walk(value, f"{path}.{key}")
            else:
                yield key, path
                yield from walk(value, f"{path}.{key}")


@pytest.mark.parametrize("model", [RhymeScript, LongScript])
def test_schema_only_uses_properties_gemini_documents(model):
    schema = to_gemini_schema(model)
    assert {k for k, _ in walk(schema)} <= _ALLOWED
    text = json.dumps(schema)
    assert "const" not in text and "pattern" not in text and "minLength" not in text


def test_schema_keeps_field_names_and_turns_const_into_enum():
    schema = to_gemini_schema(RhymeScript)
    assert schema["properties"]["format"]["enum"] == ["rhyme"]
    assert "style_prompt" in schema["$defs"]["RhymeBody"]["properties"]
    assert "anyOf" not in schema  # esquema del formato concreto, no la unión


# --- llamada y reintentos ----------------------------------------------------------------------


def test_generate_sends_model_prompt_and_json_config():
    c, sdk, sleeps = client("{}")
    assert c.generate("hola", SCHEMA) == "{}"
    req = sdk.models.requests[0]
    assert req["model"] == "gemini-test" and req["contents"] == "hola"
    assert req["config"].response_mime_type == "application/json"
    assert req["config"].response_json_schema == SCHEMA
    assert c.calls == 1 and sleeps == []


def test_rate_limit_recovers_with_growing_waits():
    c, _, sleeps = client(api_error(429), api_error(429), "ok")
    assert c.generate("p", SCHEMA) == "ok"
    assert sleeps == [2, 4] and c.calls == 3


def test_rate_limit_that_never_recovers_explains_quota_reset():
    c, _, sleeps = client(*[api_error(429)] * 4)
    with pytest.raises(EvergreenError) as e:
        c.generate("p", SCHEMA)
    assert "límite de uso" in str(e.value) and "medianoche" in str(e.value)
    assert sleeps == [2, 4, 8] and c.calls == 4


def test_overloaded_service_is_retried_too():
    c, _, _ = client(api_error(503, "UNAVAILABLE"), "ok")
    assert c.generate("p", SCHEMA) == "ok"


@pytest.mark.parametrize(
    ("code", "expected"), [(400, "400"), (401, "clave"), (403, "clave"), (500, "500")]
)
def test_other_errors_are_not_retried(code, expected):
    c, _, sleeps = client(api_error(code, message="mal"))
    with pytest.raises(EvergreenError, match=expected):
        c.generate("p", SCHEMA)
    assert c.calls == 1 and sleeps == []


def test_call_budget_counts_retries():
    c, _, _ = client(*[api_error(429)] * 6, max_calls=2)
    with pytest.raises(EvergreenError, match="tope de 2 llamadas"):
        c.generate("p", SCHEMA)
    assert c.calls == 2


def test_the_key_never_appears_in_error_messages():
    c, _, _ = client(api_error(400, message=f"clave {KEY} inválida"))
    with pytest.raises(EvergreenError) as e:
        c.generate("p", SCHEMA)
    assert KEY not in str(e.value) and "***" in str(e.value)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (response(None, finish_reason="SAFETY"), "SAFETY"),
        (response(None, block_reason="PROHIBITED_CONTENT"), "PROHIBITED_CONTENT"),
        (response(""), "desconocido"),
    ],
)
def test_empty_reply_says_why_and_is_not_retried(reply, expected):
    c, _, _ = client(reply)
    with pytest.raises(EvergreenError, match=expected):
        c.generate("p", SCHEMA)
    assert c.calls == 1


# --- generación con validación y reparación ----------------------------------------------------


def test_valid_first_reply_costs_one_call():
    c, sdk, _ = client(GOOD)
    script = generate_script(c, "prompt", "rhyme", Language.es)
    assert script.title == "Los patitos" and c.calls == 1
    assert "style_prompt" in json.dumps(
        sdk.models.requests[0]["config"].response_json_schema
    )


def test_long_format_asks_for_the_long_schema():
    c, sdk, _ = client(json.dumps(long_data()))
    generate_script(c, "prompt", "long", Language.es)
    assert "scenes" in json.dumps(sdk.models.requests[0]["config"].response_json_schema)


def test_invalid_reply_gets_exactly_one_repair_attempt():
    c, sdk, _ = client("Claro, aquí tienes", GOOD)
    assert generate_script(c, "prompt", "rhyme", Language.es).title == "Los patitos"
    repair = sdk.models.requests[1]["contents"]
    assert (
        c.calls == 2
        and "no es JSON válido" in repair
        and "Claro, aquí tienes" in repair
    )


def test_wrong_language_goes_through_repair():
    c, _, _ = client(json.dumps(rhyme_data("en")), GOOD)
    assert generate_script(c, "prompt", "rhyme", Language.es).language == Language.es
    assert c.calls == 2


def test_two_invalid_replies_fail_and_keep_the_raw_text():
    c, _, _ = client("uno", "dos")
    with pytest.raises(InvalidResponse) as e:
        generate_script(c, "prompt", "rhyme", Language.es)
    assert e.value.raw == "dos" and c.calls == 2
