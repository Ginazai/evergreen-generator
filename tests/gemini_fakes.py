"""Sustitutos del SDK de Gemini: respuestas programadas, sin red."""

from types import SimpleNamespace

from google.genai import errors


def api_error(code: int, status: str = "ERROR", message: str = "fallo"):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


def response(text, finish_reason=None, block_reason=None):
    candidates = (
        [SimpleNamespace(finish_reason=SimpleNamespace(name=finish_reason))]
        if finish_reason
        else []
    )
    feedback = (
        SimpleNamespace(block_reason=SimpleNamespace(name=block_reason))
        if block_reason
        else None
    )
    return SimpleNamespace(text=text, candidates=candidates, prompt_feedback=feedback)


class FakeModels:
    def __init__(self, script):
        self.script = list(script)  # str | response | Exception, en orden
        self.requests = []

    def generate_content(self, *, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return response(item) if isinstance(item, str) else item


class FakeSDK:
    def __init__(self, *script):
        self.models = FakeModels(script)


def wav_bytes(seconds=1.0, rate=8000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(rate * seconds))
    return buf.getvalue()


class FakeInteractions:
    def __init__(self, script):
        self.script = list(script)  # bytes | Exception | None (sin audio), en orden
        self.requests = []

    def create(self, **body):
        import base64

        self.requests.append(body)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        data = None if item is None else base64.b64encode(item).decode()
        return SimpleNamespace(
            output_audio=SimpleNamespace(data=data) if data else None
        )


class FakeTtsSDK:
    def __init__(self, *script):
        self.interactions = FakeInteractions(script)
