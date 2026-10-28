"""Comprobación única (V2 de visuals): ¿qué acepta y devuelve Cloudflare Workers AI?

Uso: docker compose run --rm app python -m evergreen.visuals.probe
Antes y después, mira en el panel de Cloudflare (Workers AI > uso) cuántas neuronas se gastaron.
Guarda las imágenes en <proyectos>/_img_probe/.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from evergreen.visuals.images import image_info

PROMPT = (
    "children's picture book illustration, flat colors, soft pastel palette, friendly rounded "
    "shapes, simple background, no text. A small yellow duckling with red boots swims in a calm pond."
)
BASE = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/{model}"


def multipart(fields: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = (
        b"".join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in fields.items()
        )
        + f"--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def call(account: str, token: str, model: str, *, json_body=None, form=None):
    if form is not None:
        body, ctype = multipart(form)
    else:
        body, ctype = json.dumps(json_body).encode(), "application/json"
    req = urllib.request.Request(
        BASE.format(account=account, model=model),
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def decode(raw: bytes, ctype: str) -> bytes:
    """La API devuelve JSON con `image` en base64 (envuelto en `result` por REST), o la imagen directa."""
    if ctype.startswith("image/"):
        return raw
    data = json.loads(raw)
    print("  claves de la respuesta:", list(data), "| success:", data.get("success"))
    result = data.get("result", data)
    return base64.b64decode(result["image"])


def main() -> None:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account or not token:
        raise SystemExit("Faltan CLOUDFLARE_ACCOUNT_ID y CLOUDFLARE_API_TOKEN en .env")
    out = Path(os.environ.get("EVERGREEN_PROJECTS_DIR", ".")) / "_img_probe"
    out.mkdir(parents=True, exist_ok=True)
    tests = [
        (
            "flux-1-schnell (JSON)",
            "flux-1-schnell",
            {"json_body": {"prompt": PROMPT, "steps": 4}},
        ),
        (
            "flux-2-klein-4b 1280x720 (multipart)",
            "flux-2-klein-4b",
            {"form": {"prompt": PROMPT, "width": 1280, "height": 720}},
        ),
        (
            "flux-2-klein-4b 720x1280 (multipart)",
            "flux-2-klein-4b",
            {"form": {"prompt": PROMPT, "width": 720, "height": 1280}},
        ),
    ]
    for n, (name, model, kwargs) in enumerate(tests, 1):
        print(f"\n== {name} ==")
        start = time.perf_counter()
        try:
            status, ctype, raw = call(account, token, model, **kwargs)
            image = decode(raw, ctype)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace").replace(token, "***")[:800]
            print(f"  ERROR HTTP {e.code}: {detail}")
            continue
        except Exception as e:  # noqa: BLE001 - script de diagnóstico: mostrar todo error
            print("  ERROR:", type(e).__name__, str(e).replace(token, "***")[:500])
            continue
        info = image_info(image)
        path = out / f"{n}-{model}.{info[0] if info else 'bin'}"
        path.write_bytes(image)
        print(
            f"  HTTP {status}, {ctype}, {len(image)} bytes, {time.perf_counter() - start:.1f} s"
        )
        print(f"  imagen: {info}  ->  {path.name}")
    print(f"\nArchivos en {out}")


if __name__ == "__main__":
    main()
