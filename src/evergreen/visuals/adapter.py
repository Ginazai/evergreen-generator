"""Etapas `visuals`, `characters` y `scenes`: Cloudflare si hay credenciales; si no, paso manual."""

import os
from collections.abc import Callable
from pathlib import Path

from evergreen import fsutil
from evergreen import manifest as mf
from evergreen.adapters.base import StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script
from evergreen.visuals.cloudflare import ImageClient, QuotaExceeded
from evergreen.visuals.images import image_info, shrink
from evergreen.visuals.manual import (
    IMAGE_EXTENSIONS,
    ImageManualAdapter,
    collect,
    find_file,
    finish,
)
from evergreen.visuals.prompts import ImageRequest, plan_images
from evergreen.visuals.style import load_style

SIZES = {"16:9": (1280, 720), "9:16": (720, 1280)}
SHEET_SIZE = (768, 768)
MODES = ("cloudflare", "manual")


class CloudflareImageAdapter:
    name = "cloudflare"

    def __init__(
        self,
        client_factory: Callable[[str, str], ImageClient] | None = None,
        shrink_fn: Callable[[Path], bytes] = shrink,
    ) -> None:
        self._factory = client_factory or ImageClient
        self._shrink = shrink_fn

    def run(self, ctx: StageContext) -> StageResult:
        script_path = ctx.video_dir / "stages" / "script" / "script.json"
        if not script_path.is_file():
            raise EvergreenError(
                "No encuentro el guion: ejecuta primero la etapa `script`."
            )
        try:
            requests = plan_images(
                ctx.stage,
                read_script(script_path),
                load_style(ctx.video_dir.parent),
                with_refs=True,
            )
        except ValueError as e:
            raise EvergreenError(str(e)) from e
        aspect = mf.aspect_of(ctx.manifest)
        (ctx.stage_dir / "inbox").mkdir(parents=True, exist_ok=True)

        _, missing, _ = collect(ctx, requests, aspect)
        client = None
        for done, request in enumerate(r for r in requests if r.key in missing):
            client = client or self._factory(
                os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
                os.environ.get("CLOUDFLARE_API_TOKEN", "").strip(),
            )
            prompt, refs = self._with_refs(ctx, request)
            size = SHEET_SIZE if request.sheet else SIZES[aspect]
            try:
                image = client.generate(prompt, size, refs)
            except QuotaExceeded as e:
                raise EvergreenError(
                    f"{e} Se generaron {len(requests) - len(missing) + done} de {len(requests)} "
                    "imágenes; al volver a ejecutar `evergreen run` se retoma. También puedes pasar "
                    "a manual (EVERGREEN_IMAGE_MODE=manual): MANUAL.md listará solo las que faltan."
                ) from e
            self._save(ctx.stage_dir, request.key, image)

        entries, missing, problem = collect(ctx, requests, aspect)
        if missing:
            raise EvergreenError(problem or f"Faltan imágenes: {', '.join(missing)}.")
        return finish(ctx, entries)

    def _with_refs(self, ctx: StageContext, request: ImageRequest):
        """Prompt y bytes de referencia. Todas o ninguna: los índices del prompt deben coincidir."""
        dirs = [ctx.stage_dir, ctx.stage_dir / "inbox"]
        characters = ctx.video_dir / "stages" / "characters"
        dirs += [characters, characters / "inbox"]
        paths = [
            next(
                (
                    p
                    for d in dirs
                    if (p := find_file(d, f"personaje-{cid}", IMAGE_EXTENSIONS))
                ),
                None,
            )
            for cid in request.refs
        ]
        if not request.refs or None in paths:
            return request.prompt, []
        try:
            return f"{request.prompt} {request.ref_text}", [
                self._shrink(p) for p in paths
            ]
        except RuntimeError as e:
            raise EvergreenError(str(e)) from e

    @staticmethod
    def _save(stage_dir: Path, key: str, image: bytes) -> None:
        info = image_info(image)
        if info is None:
            raise EvergreenError(
                f"Cloudflare devolvió algo que no es una imagen para `{key}`."
            )
        part = stage_dir / f"{key}.part"
        part.write_bytes(image)
        fsutil.replace(
            part, stage_dir / f"{key}.{'jpg' if info[0] == 'jpeg' else info[0]}"
        )


class ImageAdapter:
    """Elige el modo según EVERGREEN_IMAGE_MODE; sin él, Cloudflare si hay credenciales."""

    def __init__(self, cloudflare: CloudflareImageAdapter | None = None) -> None:
        self._cloudflare = cloudflare or CloudflareImageAdapter()
        self._manual = ImageManualAdapter()

    @staticmethod
    def _mode() -> str:
        explicit = os.environ.get("EVERGREEN_IMAGE_MODE", "").strip().lower()
        if explicit:
            return explicit
        has_keys = all(
            os.environ.get(v, "").strip()
            for v in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
        )
        return "cloudflare" if has_keys else "manual"

    @property
    def name(self) -> str:
        return self._mode()

    def run(self, ctx: StageContext) -> StageResult:
        mode = self._mode()
        if mode not in MODES:
            raise EvergreenError(
                f"EVERGREEN_IMAGE_MODE='{mode}' no es válido. Usa: {', '.join(MODES)}."
            )
        if mode == "cloudflare":
            if not all(
                os.environ.get(v, "").strip()
                for v in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
            ):
                raise EvergreenError(
                    "EVERGREEN_IMAGE_MODE=cloudflare necesita CLOUDFLARE_ACCOUNT_ID y "
                    "CLOUDFLARE_API_TOKEN en .env."
                )
            return self._cloudflare.run(ctx)
        return self._manual.run(ctx)
