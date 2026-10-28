"""Cliente delgado de Cloudflare Workers AI (FLUX.2 klein 4B). Sin SDK: solo la biblioteca estándar."""

import base64
import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable

from evergreen.errors import EvergreenError

URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
MAX_CALLS = 100  # tope por ejecución, reintentos incluidos (la cuota gratuita rinde ≈ 96 imágenes)
RETRY_DELAYS = (10, 20)
TIMEOUT = 180


class QuotaExceeded(EvergreenError):
    """Se agotó la cuota gratuita diaria de Cloudflare (o el tope de llamadas de la ejecución)."""


class HttpFailure(Exception):
    def __init__(self, code: int, text: str):
        super().__init__(f"HTTP {code}")
        self.code, self.text = code, text


def multipart(fields: dict, files: dict | None = None) -> tuple[bytes, str]:
    """`files`: {campo: (nombre de archivo, bytes, tipo)}."""
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in fields.items()
    ]
    for k, (filename, data, ctype) in (files or {}).items():
        head = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; '
            f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'
        )
        parts += [head.encode(), data, b"\r\n"]
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def _http_post(url: str, headers: dict, body: bytes) -> tuple[str, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as e:
        raise HttpFailure(e.code, e.read().decode("utf-8", "replace")) from e


class ImageClient:
    def __init__(
        self,
        account: str,
        token: str,
        *,
        post: Callable = _http_post,
        sleep: Callable[[float], None] = time.sleep,
        max_calls: int = MAX_CALLS,
    ) -> None:
        self._account, self._token = account, token
        self._post, self._sleep, self._max_calls = post, sleep, max_calls
        self.calls = 0

    def generate(
        self, prompt: str, size: tuple[int, int], refs: list[bytes] = ()
    ) -> bytes:
        """Devuelve la imagen (JPEG). Reintenta fallos pasajeros; la cuota diaria no."""
        form = {"prompt": prompt, "width": size[0], "height": size[1]}
        files = {
            f"input_image_{i}": (f"ref{i}.jpg", data, "image/jpeg")
            for i, data in enumerate(refs)
        }
        body, ctype = multipart(form, files)
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": ctype}
        delays = iter(RETRY_DELAYS)
        while True:
            if self.calls >= self._max_calls:
                raise QuotaExceeded(
                    f"Se alcanzó el tope de {self._max_calls} llamadas de imagen para esta ejecución."
                )
            self.calls += 1
            try:
                response_type, raw = self._post(
                    URL.format(account=self._account), headers, body
                )
            except HttpFailure as e:
                delay = next(delays, None)
                if (
                    e.code in (429, 500, 502, 503)
                    and delay is not None
                    and not self._daily(e)
                ):
                    self._sleep(delay)
                    continue
                raise self._explain(e) from e
            return self._image(response_type, raw)

    @staticmethod
    def _daily(e: HttpFailure) -> bool:
        # shortcut: se adivina por el texto del error (no probado); si cambia, se reintenta de más
        # y el tope de llamadas lo detiene.
        text = e.text.lower()
        return any(w in text for w in ("daily", "neurons", "allocation", "quota"))

    def _image(self, response_type: str, raw: bytes) -> bytes:
        if response_type.startswith("image/"):
            return raw
        try:
            data = json.loads(raw)
            result = data.get("result", data)
            return base64.b64decode(result["image"])
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise EvergreenError(
                "Cloudflare no devolvió una imagen en el formato esperado."
            ) from e

    def _explain(self, e: HttpFailure) -> EvergreenError:
        detail = e.text.replace(self._token, "***")[:300]
        if e.code == 429 or self._daily(e):
            return QuotaExceeded(
                "Cloudflare rechazó la solicitud por cuota (el límite gratuito se reinicia a las "
                f"00:00 UTC). Detalle: {detail}"
            )
        if e.code in (401, 403):
            return EvergreenError(
                f"Cloudflare no aceptó el token ({e.code}). Revisa CLOUDFLARE_API_TOKEN y que "
                "tenga permiso de Workers AI."
            )
        return EvergreenError(f"Error de Cloudflare ({e.code}): {detail}")
