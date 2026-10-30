"""Interfaz Streamlit: solo presenta y llama al núcleo; no tiene lógica de negocio propia."""

import json
import shutil
from pathlib import Path

import streamlit as st

from evergreen import (
    assembly,
    config,
    editing,
    jobs,
    project,
    reopen,
    runner,
    script_writer,
    visuals,
    voice_audio,
)
from evergreen import manifest as mf
from evergreen.errors import EvergreenError

STATUS = {
    "pending": ":gray-badge[pendiente]", "running": ":blue-badge[en curso]",
    "awaiting_manual": ":orange-badge[paso manual]", "awaiting_approval": ":orange-badge[por aprobar]",
    "done": ":green-badge[lista]", "failed": ":red-badge[falló]",
}  # fmt: skip
PIPE = {
    "done": "done",
    "running": "run",
    "awaiting_manual": "wait",
    "awaiting_approval": "wait",
    "failed": "fail",
}
BRAND = (
    '<div class="brand"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 6 10h3l-4 6h4l-3 5h12l-3-5h4l-4-6h3z"/></svg>'
    "Evergreen</div>"
)
HINTS = {
    "EVERGREEN_VOICE_MODE": "gemini, piper o manual",
    "EVERGREEN_IMAGE_MODE": "cloudflare o manual",
}
ITEM_STAGES = {"voice", "visuals", "characters", "scenes"}
EXAMPLES = {
    "cast": "cast.example.yaml",
    "voices": "voices.example.yaml",
    "style": "style.example.yaml",
}
CSS = Path(__file__).with_name("style.css")
for _m in (script_writer, voice_audio, visuals, assembly):
    _m.register()


def attempt(fn, *args):
    """Ejecuta una acción del núcleo; un error esperado se muestra, no rompe la página."""
    try:
        return fn(*args), True
    except EvergreenError as e:
        st.error(str(e))
        return None, False


def act(label, key, fn, *args, **kw):
    if st.button(label, key=key, **kw):
        _, ok = attempt(fn, *args)
        if ok:
            st.rerun()


def items(video_dir: Path, stage: str) -> list[str]:
    """Elementos regenerables de una etapa: claves de imágenes o archivos de audio."""
    d = video_dir / "stages" / stage
    for name, field in (("images.json", "key"), ("timeline.json", "file")):
        if (d / name).is_file():
            rows = json.loads((d / name).read_text(encoding="utf-8"))
            return [Path(r[field]).stem for r in rows]
    return []


def regenerate_and_run(video_dir: Path, stage: str, keys: list[str]) -> None:
    """Archiva esos elementos y retoma la etapa: los adaptadores solo producen lo que falta."""
    reopen.regenerate_items(video_dir, stage, keys)
    jobs.start(video_dir)


def preview(video_dir: Path, stage: str, state: mf.StageState) -> None:
    d = video_dir / "stages" / stage
    if (d / "script.md").is_file():
        st.markdown((d / "script.md").read_text(encoding="utf-8"))
    for out in state.outputs:
        p = video_dir / out
        if p.suffix in (".wav", ".mp3", ".m4a") and p.is_file():
            st.caption(p.name)
            st.audio(str(p))
        elif p.suffix in (".jpg", ".png", ".webp") and p.is_file():
            st.image(str(p), caption=p.name, width=240)
        elif p.suffix == ".mp4" and p.is_file():
            st.video(str(p))
    if state.error:
        st.error(state.error)


def label(v, videos) -> str:
    """El título; con el id solo si otro video se llama igual."""
    return (
        v.title
        if sum(x.title == v.title for x in videos) == 1
        else f"{v.title} ({v.id})"
    )


def pipeline(manifest: mf.Manifest) -> None:
    """Tira de etapas: una barra por etapa, con su nombre; el color es el estado."""
    stages = manifest.stages.items()
    done = sum(s.status == mf.Status.done for _, s in stages)
    cells = "".join(
        f'<div class="s {"wait" if s.stale else PIPE.get(s.status.value, "")}"><b>{n}</b></div>'
        for n, s in stages
    )
    st.markdown(
        f'<div class="pipe" role="img" aria-label="{done} de {len(stages)} etapas listas">{cells}</div>',
        unsafe_allow_html=True,
    )


def stage_panel(video_dir: Path, name: str, state: mf.StageState, busy: bool) -> None:
    flag = " :orange-badge[desactualizada]" if state.stale else ""
    with st.expander(
        f"**{name}** {STATUS[state.status.value]}{flag}",
        expanded=state.status != mf.Status.done,
    ):
        preview(video_dir, name, state)
        if state.status == mf.Status.awaiting_approval:
            act(
                "Aprobar", f"ap-{name}", runner.approve, video_dir, name, type="primary"
            )
        if state.status == mf.Status.awaiting_manual:
            manual = video_dir / "stages" / name / "MANUAL.md"
            if manual.is_file():
                st.markdown(manual.read_text(encoding="utf-8"))
            for f in (
                st.file_uploader(
                    "Subir archivos a inbox",
                    accept_multiple_files=True,
                    key=f"up-{name}",
                )
                or []
            ):
                (video_dir / "stages" / name / "inbox").mkdir(
                    parents=True, exist_ok=True
                )
                (video_dir / "stages" / name / "inbox" / Path(f.name).name).write_bytes(
                    f.getvalue()
                )
                st.success(f"Guardado {f.name}")
        with st.container(horizontal=True):
            if state.stale:
                act("Mantener tal cual", f"keep-{name}", reopen.keep, video_dir, name)
            if state.status != mf.Status.pending and not busy:
                act(
                    "Rehacer (archiva lo anterior)",
                    f"re-{name}",
                    reopen.reopen,
                    video_dir,
                    name,
                )
        # También en "por aprobar": ahí es donde se revisa y se descubre qué salió mal.
        reviewable = (mf.Status.done, mf.Status.awaiting_approval)
        if name in ITEM_STAGES and state.status in reviewable and not busy:
            keys = items(video_dir, name)
            if keys:
                picked = st.multiselect(
                    "Regenerar solo estos (los demás no se tocan ni gastan cuota)",
                    keys,
                    key=f"sel-{name}",
                )
                if picked:
                    act(
                        f"Regenerar {len(picked)} y ejecutar",
                        f"item-{name}",
                        regenerate_and_run,
                        video_dir,
                        name,
                        picked,
                    )


@st.fragment(run_every=2)
def live_log(video_dir: Path) -> None:
    if jobs.is_running(video_dir):
        st.info("Ejecutando… puedes cerrar esta pestaña; el trabajo sigue.")
        st.code(jobs.read_log(video_dir) or "(sin salida todavía)")
    else:
        st.rerun()


def edit_script(video_dir: Path, manifest: mf.Manifest) -> None:
    path = video_dir / "stages" / "script" / "script.json"
    if not path.is_file():
        st.info("Aún no hay guion. Ejecuta la etapa `script` primero.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["title"] = st.text_input("Título del guion", data["title"])
    if manifest.format == mf.Format.long:
        for scene in data["body"]["scenes"]:
            st.markdown(f"**{scene['id']}** · {scene['setting']}")
            scene["beats"] = st.data_editor(
                scene["beats"],
                key=f"beats-{scene['id']}",
                num_rows="dynamic",
                use_container_width=True,
            )
    else:
        for i, sec in enumerate(data["body"]["sections"]):
            text = st.text_area(
                f"{sec['kind']} {i + 1} (una línea por verso)",
                "\n".join(sec["lines"]),
                key=f"sec-{i}",
            )
            sec["lines"] = [x for x in text.splitlines() if x.strip()]
    with st.expander("JSON completo (avanzado: tomas, movimiento, personajes)"):
        raw = st.text_area(
            "script.json",
            json.dumps(data, ensure_ascii=False, indent=2),
            height=300,
            key="raw",
        )
    use_raw = st.checkbox("Guardar el JSON completo de arriba en lugar del formulario")
    if st.button("Guardar guion", type="primary"):
        marked, ok = attempt(
            editing.save_script,
            video_dir,
            raw if use_raw else json.dumps(data, ensure_ascii=False),
        )
        if ok:
            st.success(
                "Guardado."
                + (f" Desactualizadas: {', '.join(marked)}." if marked else "")
            )


def video_page(root: Path) -> None:
    videos = project.list_videos(root)
    with (
        st.sidebar.expander("Nuevo video", icon=":material/add:", expanded=not videos),
        st.form("new"),
    ):
        title = st.text_input("Título")
        fmt = st.selectbox("Formato", [f.value for f in mf.Format])
        lang = st.selectbox("Idioma", [x.value for x in mf.Language])
        aspect = st.selectbox("Proporción", ["(por defecto)", "16:9", "9:16"])
        brief = st.text_area("Tema (opcional)", max_chars=mf.BRIEF_MAX)
        if st.form_submit_button("Crear"):
            _, ok = attempt(
                project.create, title, mf.Format(fmt), mf.Language(lang), root, brief,
                None if aspect.startswith("(") else aspect,
            )  # fmt: skip
            if ok:
                st.rerun()
    if not videos:
        st.info("Crea tu primer video en la barra lateral.")
        return
    ids = [v.id for v in videos]
    video_id = st.sidebar.selectbox(
        "Video",
        ids,
        format_func=lambda i: next(label(v, videos) for v in videos if v.id == i),
    )
    video_dir = root / video_id
    manifest = mf.load(video_dir / "manifest.yaml")
    st.title(manifest.title)
    st.caption(
        f"{manifest.format.value} · {manifest.language.value} · {mf.aspect_of(manifest)}"
    )
    pipeline(manifest)
    stale = [n for n, s in manifest.stages.items() if s.stale]
    if stale:
        st.warning(
            f"Desactualizadas por cambios anteriores: {', '.join(stale)}. Rehazlas o márcalas como 'mantener'."
        )
    busy = jobs.is_running(video_dir)
    tab_run, tab_edit = st.tabs(["Etapas", "Editar"])
    with tab_run:
        if busy:
            live_log(video_dir)
        else:
            act(
                "Ejecutar / continuar",
                "run",
                jobs.start,
                video_dir,
                type="primary",
                icon=":material/play_arrow:",
            )
        for name, state in manifest.stages.items():
            stage_panel(video_dir, name, state, busy)
    with tab_edit:
        with st.form("meta"):
            t = st.text_input("Título", manifest.title)
            b = st.text_area("Tema", manifest.brief or "", max_chars=mf.BRIEF_MAX)
            if st.form_submit_button("Guardar título y tema"):
                marked, ok = attempt(editing.set_title_and_brief, video_dir, t, b)
                if ok:
                    st.success(
                        "Guardado."
                        + (f" Desactualizadas: {', '.join(marked)}." if marked else "")
                    )
        edit_script(video_dir, manifest)


def config_editor(root: Path, kind: str, example: str) -> None:
    path = root / f"{kind}.yaml"
    sample = Path(__file__).resolve().parents[3] / example
    default = (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else (sample.read_text(encoding="utf-8") if sample.is_file() else "")
    )
    text = st.text_area(
        f"{kind}.yaml",
        default,
        height=360,
        key=f"cfg-{kind}",
        label_visibility="collapsed",
    )
    if st.button(f"Guardar {kind}.yaml", key=f"save-{kind}", type="primary"):
        affected, ok = attempt(editing.save_config, root, kind, text)
        if ok:
            st.success(
                "Guardado."
                + "".join(
                    f" {v}: {', '.join(s)} desactualizadas."
                    for v, s in affected.items()
                )
            )


def config_page(root: Path) -> None:
    st.title("Elenco, voces y estilo")
    st.caption("Se comparten entre todos los videos de la carpeta de proyectos.")
    tabs = st.tabs([f"{kind}.yaml" for kind in EXAMPLES])
    for tab, (kind, example) in zip(tabs, EXAMPLES.items()):
        with tab:
            config_editor(root, kind, example)


def settings_page() -> None:
    st.title("Ajustes")
    current = config.read_settings()
    values = {}
    with st.form(
        "settings", clear_on_submit=True
    ):  # la clave escrita no se queda en pantalla
        for key in config.SETTING_KEYS:
            secret = key in config.SECRET_KEYS
            values[key] = st.text_input(
                key, "" if secret else current.get(key, ""), type="password" if secret else "default",
                placeholder=config.mask(current.get(key, "")) if secret else HINTS.get(key, ""),
            )  # fmt: skip
            if secret and not values[key] and key in current:
                values[key] = current[key]  # vacío = conservar la clave guardada
        saved = st.form_submit_button("Guardar ajustes", type="primary")
    if saved:
        config.save_settings(values)
        st.success("Guardado. Para borrar una clave, elimina su línea de settings.env.")
    st.markdown(
        "ffmpeg "
        + (
            ":green-badge[instalado]"
            if shutil.which("ffmpeg")
            else ":red-badge[no instalado]"
        )
    )
    st.caption(f"Carpeta de proyectos: `{config.projects_dir()}`")


def main() -> None:
    st.set_page_config(
        page_title="Evergreen", page_icon=":material/park:", layout="wide"
    )
    st.html(f"<style>{CSS.read_text(encoding='utf-8')}</style>")
    config.load_settings()
    root = config.projects_dir()
    st.sidebar.markdown(BRAND, unsafe_allow_html=True)
    page = st.sidebar.radio(
        "Sección",
        ["Videos", "Elenco, voces y estilo", "Ajustes"],
        label_visibility="collapsed",
    )
    {
        "Videos": lambda: video_page(root),
        "Elenco, voces y estilo": lambda: config_page(root),
        "Ajustes": settings_page,
    }[page]()


main()
