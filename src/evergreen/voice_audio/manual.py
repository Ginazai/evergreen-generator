"""Etapas `song` y `music`: siempre manuales (no hay vía gratuita por API)."""

from collections.abc import Callable
from pathlib import Path

from evergreen.adapters.base import Done, NeedsManual, StageContext, StageResult
from evergreen.errors import EvergreenError
from evergreen.script_writer.models import read_script

EXTENSIONS = (".mp3", ".wav")
TAGS = {"verse": "Verse", "chorus": "Chorus", "bridge": "Bridge"}


def song_prompt(script) -> str:
    body = script.body
    lyrics = "\n\n".join(
        f"[{TAGS[s.kind]}]\n" + "\n".join(s.lines) for s in body.sections
    )
    return (
        f"Estilo (cópialo en el campo de estilo): {body.style_prompt}, "
        f"unos {body.bpm_hint} bpm\n\nLetra (idioma: {script.language.value}):\n\n{lyrics}"
    )


def music_prompt(script) -> str:
    v = script.variation
    return (
        "Música instrumental de fondo para un video infantil, sin voces ni letra.\n"
        f"Tono: {v.tone}. Ambiente: {script.body.logline}\n"
        "Suave y repetible (el montaje la repite); mejor 3 minutos o más."
    )


class AudioManualAdapter:
    name = "manual"

    def __init__(self, stem: str, build: Callable) -> None:
        self.stem, self.build = stem, build

    def _find(self, inbox: Path) -> Path | None:
        return next(
            (p for e in EXTENSIONS if (p := inbox / f"{self.stem}{e}").is_file()), None
        )

    def run(self, ctx: StageContext) -> StageResult:
        inbox = ctx.stage_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        found = self._find(inbox)
        problem = ""
        if found and found.stat().st_size == 0:
            problem = f"\n## Problema\n\n`{found.name}` está vacío. Genera el audio de nuevo.\n"
        elif found:
            (ctx.stage_dir / "MANUAL.md").unlink(missing_ok=True)
            return Done([found])

        script_path = ctx.video_dir / "stages" / "script" / "script.json"
        if not script_path.is_file():
            raise EvergreenError(
                "No encuentro el guion: ejecuta primero la etapa `script`."
            )
        text = self.build(read_script(script_path))
        (ctx.stage_dir / "MANUAL.md").write_text(
            f"# Paso manual: {ctx.stage}\n\nVideo: {ctx.manifest.title}\n\n"
            f"Genera el audio con la herramienta que prefieras y guárdalo como "
            f"`{self.stem}.mp3` o `{self.stem}.wav` en `stages/{ctx.stage}/inbox/`.\n"
            f"Después ejecuta: `evergreen run {ctx.manifest.id}`\n{problem}\n"
            f"## Texto para pegar\n\n````text\n{text}\n````\n",
            encoding="utf-8",
        )
        return NeedsManual(ctx.stage_dir / "MANUAL.md", [f"{self.stem}.mp3"])
