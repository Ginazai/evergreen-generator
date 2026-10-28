import base64
import json

import pytest
from test_images import jpeg

from evergreen.errors import EvergreenError
from evergreen.visuals.cloudflare import (
    MAX_CALLS,
    HttpFailure,
    ImageClient,
    QuotaExceeded,
    _http_post,
    multipart,
)

TOKEN = "token-secreto-123"
IMG = jpeg(1280, 720)


def ok(image=IMG):
    return "application/json", json.dumps(
        {"success": True, "result": {"image": base64.b64encode(image).decode()}}
    ).encode()


class FakePost:
    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def __call__(self, url, headers, body):
        self.requests.append((url, headers, body))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(*script, **kw):
    post, sleeps = FakePost(*script), []
    return (
        ImageClient("acct", TOKEN, post=post, sleep=sleeps.append, **kw),
        post,
        sleeps,
    )


def test_sends_multipart_with_size_and_references_and_returns_the_image():
    c, post, _ = client(ok())
    assert c.generate("un patito", (1280, 720), [b"REF0", b"REF1"]) == IMG
    url, headers, body = post.requests[0]
    assert url.endswith("/accounts/acct/ai/run/@cf/black-forest-labs/flux-2-klein-4b")
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    for piece in (
        b'name="prompt"',
        b"un patito",
        b'name="width"',
        b"1280",
        b'name="height"',
        b'name="input_image_0"',
        b"REF0",
        b'name="input_image_1"',
        b"REF1",
    ):
        assert piece in body


def test_raw_image_response_is_accepted_and_garbage_is_an_error():
    c, _, _ = client(
        ("image/jpeg", IMG),
        ("application/json", b"no es json"),
        ("application/json", b'{"result": {}}'),
    )
    assert c.generate("x", (1, 1)) == IMG
    for _ in range(2):
        with pytest.raises(EvergreenError, match="formato esperado"):
            c.generate("x", (1, 1))


def test_transient_errors_are_retried_then_surface():
    c, _, sleeps = client(HttpFailure(503, "busy"), ok())
    assert c.generate("x", (1, 1)) == IMG and sleeps == [10]
    d, _, _ = client(*[HttpFailure(500, "boom")] * 5)
    with pytest.raises(EvergreenError, match="Error de Cloudflare \\(500\\)"):
        d.generate("x", (1, 1))
    assert d.calls == 3  # 1 + 2 reintentos


def test_daily_quota_is_not_retried():
    c, _, sleeps = client(
        HttpFailure(429, '{"errors":[{"message":"daily free allocation of neurons"}]}')
    )
    with pytest.raises(QuotaExceeded, match="00:00 UTC"):
        c.generate("x", (1, 1))
    assert c.calls == 1 and sleeps == []


def test_cap_auth_errors_and_token_scrubbing():
    c, _, _ = client(ok(), ok(), max_calls=1)
    c.generate("x", (1, 1))
    with pytest.raises(QuotaExceeded, match="tope de 1"):
        c.generate("x", (1, 1))
    assert MAX_CALLS >= 96
    d, _, _ = client(HttpFailure(401, "no"))
    with pytest.raises(EvergreenError, match="CLOUDFLARE_API_TOKEN"):
        d.generate("x", (1, 1))
    e, _, _ = client(HttpFailure(400, f"error con {TOKEN}"))
    with pytest.raises(EvergreenError) as err:
        e.generate("x", (1, 1))
    assert TOKEN not in str(err.value)


def test_multipart_without_files_and_real_transport_is_blocked_in_tests():
    body, ctype = multipart({"a": 1})
    assert b'name="a"' in body and ctype.startswith("multipart/")
    with pytest.raises(AssertionError, match="red real"):
        _http_post(
            "https://example.invalid", {}, b""
        )  # el transporte real está cortado


def test_real_transport_reads_the_response_and_wraps_http_errors(monkeypatch):
    import io
    import urllib.error

    from evergreen.visuals import cloudflare

    class Resp(io.BytesIO):
        headers = {"Content-Type": "application/json"}  # noqa: RUF012

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        cloudflare.urllib.request, "urlopen", lambda req, timeout: Resp(b"{}")
    )
    assert _http_post("https://x", {}, b"") == ("application/json", b"{}")

    def fail(req, timeout):
        raise urllib.error.HTTPError("https://x", 429, "no", {}, io.BytesIO(b"cuota"))

    monkeypatch.setattr(cloudflare.urllib.request, "urlopen", fail)
    with pytest.raises(HttpFailure) as e:
        _http_post("https://x", {}, b"")
    assert e.value.code == 429 and e.value.text == "cuota"
