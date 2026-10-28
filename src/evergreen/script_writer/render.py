"""script.json -> script.md: la versión legible para revisar el guion."""

from evergreen.script_writer.models import RhymeScript

KIND_ES = {"verse": "Verso", "chorus": "Estribillo", "bridge": "Puente"}


def render_markdown(script) -> str:
    v = script.variation
    names = {c.id: c.name for c in script.characters}
    out = [
        f"# {script.title}",
        "",
        f"Formato: {script.format} · Idioma: {script.language.value}",
        f"Variación: {v.structure} · {v.tone} · {v.twist}",
        "",
        "## Personajes",
        "",
    ]
    out += [
        f"- **{c.name}** (`{c.id}`): {c.visual.rstrip('.')}. Voz: {c.voice.rstrip('.')}."
        for c in script.characters
    ]

    if isinstance(script, RhymeScript):
        body = script.body
        out += [
            "",
            "## Música",
            "",
            f"{body.style_prompt} (≈{body.bpm_hint} bpm)",
            "",
            "## Letra",
        ]
        seen: dict[str, int] = {}
        for section in body.sections:
            seen[section.kind] = seen.get(section.kind, 0) + 1
            out += ["", f"### {KIND_ES[section.kind]} {seen[section.kind]}", ""]
            out += [f"{line}  " for line in section.lines]
        out += ["", "## Tomas", ""]
        for i, shot in enumerate(body.shots, 1):
            who = ", ".join(names[c] for c in shot.characters)
            out.append(
                f"{i}. (sección {shot.section_index + 1}) {shot.description}"
                + (f" — {who}" if who else "")
                + (f" · movimiento: {shot.motion}" if shot.motion else "")
            )
    else:
        out += ["", "## Resumen", "", script.body.logline]
        for n, scene in enumerate(script.body.scenes, 1):
            out += [
                "",
                f"## Escena {n}: {scene.setting}",
                "",
                f"_{scene.visual_notes}_",
                "",
            ]
            out += [
                f"- **{names.get(b.speaker, 'Narrador')}** ({b.emotion}): {b.text}"
                for b in scene.beats
            ]
            if scene.shots:
                out += ["", "Tomas:"]
                out += [
                    f"{i}. (desde el diálogo {s.beat_index + 1}) {s.description}"
                    + (f" · movimiento: {s.motion}" if s.motion else "")
                    for i, s in enumerate(scene.shots, 1)
                ]
    return "\n".join(out) + "\n"
