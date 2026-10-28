from typing import Annotated

import typer

from evergreen import (
    __version__,
    assembly,
    config,
    project,
    runner,
    script_writer,
    visuals,
    voice_audio,
)
from evergreen import manifest as mf
from evergreen import (
    reopen as reopen_mod,
)
from evergreen.errors import EvergreenError
from evergreen.manifest import Format, Language

app = typer.Typer(help="Generador de contenido evergreen.", no_args_is_help=True)
script_writer.register()
voice_audio.register()
visuals.register()
assembly.register()

STATUS_ES = {
    "pending": "pendiente",
    "running": "en ejecución",
    "awaiting_manual": "esperando paso manual",
    "awaiting_approval": "esperando aprobación",
    "done": "listo",
    "failed": "falló",
}


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True)
    ] = False,
) -> None:
    """Punto de entrada; los subcomandos se añaden por tarea."""
    config.load_settings()


@app.command()
def new(
    title: Annotated[str, typer.Argument(help="Título del video")],
    format: Annotated[
        Format, typer.Option(help="rhyme (rima/short) o long (video largo)")
    ],
    language: Annotated[Language, typer.Option(help="es o en")] = Language.es,
    brief: Annotated[
        str | None,
        typer.Option(help="Tema o notas para el guion (máx. 500 caracteres)"),
    ] = None,
    aspect: Annotated[
        mf.Aspect | None,
        typer.Option(help="Proporción: 16:9 o 9:16 (por defecto según el formato)"),
    ] = None,
) -> None:
    """Crea la carpeta de un video nuevo con su manifest."""
    folder = _guard(
        lambda: project.create(
            title, format, language, config.projects_dir(), brief, aspect
        )
    )
    typer.echo(f"Creado: {folder.name}")


def _guard(fn):
    try:
        return fn()
    except EvergreenError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


def _print_stages(manifest: mf.Manifest) -> None:
    for name, st in manifest.stages.items():
        line = f"  {name}: {STATUS_ES[st.status.value]}{' (desactualizada)' if st.stale else ''}"
        typer.echo(f"{line} ({st.error})" if st.error else line)


@app.command()
def run(video_id: Annotated[str, typer.Argument(help="Id del video")]) -> None:
    """Ejecuta (o reanuda) el pipeline de un video."""
    folder = _guard(lambda: project.open_video(video_id, config.projects_dir()))
    manifest = _guard(lambda: runner.run(folder))
    _print_stages(manifest)
    if any(st.status == mf.Status.failed for st in manifest.stages.values()):
        raise typer.Exit(1)


@app.command()
def approve(
    video_id: Annotated[str, typer.Argument(help="Id del video")],
    stage: Annotated[str, typer.Argument(help="Etapa a aprobar")],
) -> None:
    """Aprueba una etapa que espera aprobación para que el pipeline continúe."""
    folder = _guard(lambda: project.open_video(video_id, config.projects_dir()))
    _guard(lambda: runner.approve(folder, stage))
    typer.echo(f"Aprobada: {stage}")


@app.command()
def reopen(
    video_id: Annotated[str, typer.Argument(help="Id del video")],
    stage: Annotated[str, typer.Argument(help="Etapa a rehacer")],
) -> None:
    """Rehace una etapa (archiva lo anterior) y marca como desactualizado lo que depende de ella."""
    folder = _guard(lambda: project.open_video(video_id, config.projects_dir()))
    stale = _guard(lambda: reopen_mod.reopen(folder, stage))
    typer.echo(f"Reabierta: {stage}")
    if stale:
        typer.echo(f"Desactualizadas: {', '.join(stale)}")


@app.command()
def status(video_id: Annotated[str, typer.Argument(help="Id del video")]) -> None:
    """Muestra el estado de cada etapa."""
    folder = _guard(lambda: project.open_video(video_id, config.projects_dir()))
    _print_stages(mf.load(folder / "manifest.yaml"))


@app.command("list")
def list_() -> None:
    """Lista los videos existentes."""
    videos = project.list_videos(config.projects_dir())
    if not videos:
        typer.echo("No hay videos todavía.")
    for m in videos:
        done = sum(st.status == mf.Status.done for st in m.stages.values())
        typer.echo(f"{m.id}  {m.title}  ({done}/{len(m.stages)} etapas)")
