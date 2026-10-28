from evergreen.adapters.base import Done, NeedsManual, StageContext, StageResult


class ManualAdapter:
    """Pide un paso manual: el usuario deja los archivos en inbox/ y vuelve a ejecutar."""

    name = "manual"

    def __init__(self, expected_files: list[str]) -> None:
        self.expected_files = expected_files

    def run(self, ctx: StageContext) -> StageResult:
        inbox = ctx.stage_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        instructions = ctx.stage_dir / "MANUAL.md"

        missing = [f for f in self.expected_files if not (inbox / f).exists()]
        if not missing:
            instructions.unlink(missing_ok=True)
            return Done([inbox / f for f in self.expected_files])

        files = "\n".join(f"- `{f}`" for f in missing)
        instructions.write_text(
            f"# Paso manual: {ctx.stage}\n\n"
            f"Video: {ctx.manifest.title} (idioma: {ctx.manifest.language.value})\n\n"
            f"Genera esta etapa con la herramienta que prefieras y deja en "
            f"`stages/{ctx.stage}/inbox/` estos archivos:\n\n{files}\n\n"
            f"Después ejecuta: `evergreen run {ctx.manifest.id}`\n",
            encoding="utf-8",
        )
        return NeedsManual(instructions, missing)
