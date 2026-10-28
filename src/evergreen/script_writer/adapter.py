import json
import os
from collections.abc import Callable
from pathlib import Path

from evergreen.adapters.base import Done, NeedsManual, StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.cast import apply_cast, load_cast
from evergreen.script_writer.models import Variation, parse_script
from evergreen.script_writer.prompts import build_prompt
from evergreen.script_writer.render import render_markdown
from evergreen.script_writer.variation import (
    SIMILARITY_THRESHOLD,
    existing_scripts,
    find_similar,
    pick_variation,
)

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # gratis: 500 solicitudes/día (3.8-flash: 20); cambia con GEMINI_MODEL
ATTEMPTS = 3  # 1 generación + hasta 2 regeneraciones por parecerse a otro video
# Windows puede guardar "script.json.txt" desde el Bloc de notas.
INBOX_NAMES = ("script.json", "script.json.txt")

INSTRUCTIONS = """# Paso manual: guion

Video: {title} (formato: {format}, idioma: {language})

## Qué hacer

1. Copia el prompt de más abajo y pégalo en el chat que prefieras (Gemini, Claude, ChatGPT...).
2. Guarda la respuesta (solo el JSON) como `script.json` dentro de `stages/script/inbox/`.
   En Windows, con el Bloc de notas: Archivo > Guardar como > Tipo: "Todos los archivos" y
   nombre `script.json` (si no, queda como `script.json.txt`; también lo aceptamos).
   Si el chat envuelve la respuesta en ```json ... ```, no pasa nada.
3. Ejecuta `evergreen run {id}`.
{problem}
## Prompt

````text
{prompt}````
"""


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # "Unicode" del Bloc de notas
            return data.decode("utf-16")
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise EvergreenError(
            "No pude leer el archivo como texto UTF-8. Guárdalo de nuevo con codificación UTF-8."
        ) from e


def _threshold() -> float:
    raw = os.environ.get("EVERGREEN_SIMILARITY_THRESHOLD", "").strip()
    try:
        return float(raw) if raw else SIMILARITY_THRESHOLD
    except ValueError:
        raise EvergreenError(
            "EVERGREEN_SIMILARITY_THRESHOLD debe ser un número, por ejemplo 0.35."
        ) from None


class ScriptAdapter:
    """Etapa `script`: Gemini si hay clave; si no, paso manual con el prompt listo en MANUAL.md."""

    def __init__(
        self, client_factory: Callable[[str, str], object] | None = None
    ) -> None:
        self._client_factory = (
            client_factory  # inyectable: las pruebas usan un SDK ficticio
        )

    @property
    def name(self) -> str:
        return "manual" if self._manual_mode() else "gemini"

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("GEMINI_API_KEY", "").strip()

    def _manual_mode(self) -> bool:
        forced = os.environ.get("EVERGREEN_SCRIPT_MODE", "").strip().lower() == "manual"
        return forced or not self._api_key()

    def run(self, ctx: StageContext) -> StageResult:
        return self._run_manual(ctx) if self._manual_mode() else self._run_api(ctx)

    # --- modo API -------------------------------------------------------------------------

    def _run_api(self, ctx: StageContext) -> StageResult:
        from evergreen.script_writer.gemini import (
            GeminiClient,
            InvalidResponse,
            generate_script,
        )

        model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
        factory = self._client_factory or GeminiClient
        client = factory(
            self._api_key(), model
        )  # un cliente por ejecución: el tope de llamadas es por etapa
        fmt, language = ctx.manifest.format.value, ctx.manifest.language
        threshold = _threshold()
        cast = load_cast(ctx.video_dir.parent)
        others = existing_scripts(ctx.video_dir.parent, exclude=ctx.video_dir.name)
        avoid = [s.variation for _, s in others]

        similar = None
        for attempt in range(1, ATTEMPTS + 1):
            variation = pick_variation(fmt, avoid=avoid)
            prompt = build_prompt(ctx.manifest, variation, cast)
            try:
                script = generate_script(client, prompt, fmt, language)
            except InvalidResponse as e:
                (ctx.stage_dir / "raw.txt").write_text(e.raw, encoding="utf-8")
                raise
            finally:  # cuántas llamadas gastó, aunque falle (cuota gratuita)
                (ctx.stage_dir / "generation.json").write_text(
                    json.dumps(
                        {"model": model, "attempt": attempt, "calls": client.calls}
                    ),
                    encoding="utf-8",
                )
            # La variación es nuestra: la del prompt, no la que devolvió el modelo.
            script = script.model_copy(update={"variation": variation})
            if cast:
                script = apply_cast(script, cast)
            similar = find_similar(script, others, threshold)
            if similar is None:
                return self._finish(ctx, script)
            avoid.append(variation)  # la siguiente regeneración prueba otra combinación

        video_id, score = similar
        raise EvergreenError(
            f"El guion se parece demasiado al del video '{video_id}' (similitud {score:.2f}) "
            f"tras {ATTEMPTS} intentos. Vuelve a ejecutar `evergreen run` para probar otra variación."
        )

    # --- modo manual ----------------------------------------------------------------------

    def _run_manual(self, ctx: StageContext) -> StageResult:
        inbox = ctx.stage_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        variation = self._variation(ctx)
        cast = load_cast(ctx.video_dir.parent)

        problem = None
        found = next((p for n in INBOX_NAMES if (p := inbox / n).is_file()), None)
        if found:
            try:
                script = parse_script(
                    _read_text(found), ctx.manifest.format.value, ctx.manifest.language
                )
                if cast:
                    script = apply_cast(script, cast)
            except EvergreenError as e:
                problem = str(e)
            else:
                # La variación es nuestra: la elegida para el prompt, no la que devolvió el chat.
                return self._finish(
                    ctx, script.model_copy(update={"variation": variation})
                )

        self._write_instructions(ctx, variation, problem, cast)
        return NeedsManual(ctx.stage_dir / "MANUAL.md", ["script.json"])

    def _variation(self, ctx: StageContext) -> Variation:
        """Estable entre ejecuciones: la elegida al escribir el prompt es la que se registra."""
        path = ctx.stage_dir / "variation.json"
        if path.is_file():
            try:
                return Variation.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        others = existing_scripts(ctx.video_dir.parent, exclude=ctx.video_dir.name)
        variation = pick_variation(
            ctx.manifest.format.value, avoid=[s.variation for _, s in others]
        )
        path.write_text(variation.model_dump_json(), encoding="utf-8")
        return variation

    def _write_instructions(
        self,
        ctx: StageContext,
        variation: Variation,
        problem: str | None,
        cast=None,
    ):
        m = ctx.manifest
        text = INSTRUCTIONS.format(
            title=m.title,
            format=m.format.value,
            language=m.language.value,
            id=m.id,
            problem=(
                f"\n## Problema con tu archivo\n\n{problem}\n\n"
                "Corrígelo o genera otra respuesta y vuelve a ejecutar.\n"
                if problem
                else ""
            ),
            prompt=build_prompt(m, variation, cast),
        )
        (ctx.stage_dir / "MANUAL.md").write_text(text, encoding="utf-8")

    # --- común ----------------------------------------------------------------------------

    def _finish(self, ctx: StageContext, script) -> Done:
        json_path, md_path = ctx.stage_dir / "script.json", ctx.stage_dir / "script.md"
        json_path.write_text(
            json.dumps(script.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(script), encoding="utf-8")
        for leftover in ("MANUAL.md", "variation.json", "raw.txt"):
            (ctx.stage_dir / leftover).unlink(missing_ok=True)
        return Done([json_path, md_path])
