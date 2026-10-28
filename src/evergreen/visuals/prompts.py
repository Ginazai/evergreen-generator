"""Del guion a la lista de imágenes: sin llamar a ningún modelo, solo texto determinista."""

from dataclasses import dataclass

from evergreen.script_writer.models import NARRATOR, LongScript, RhymeScript
from evergreen.visuals.style import Style

STAGES = {"visuals": RhymeScript, "characters": LongScript, "scenes": LongScript}


@dataclass(frozen=True)
class ImageRequest:
    key: str  # nombre del archivo sin extensión
    prompt: str
    negative: str
    motion: str | None = None  # prompt para animar la imagen (clip manual)
    priority: bool = False  # buen candidato a clip: gasta antes los créditos de Flow
    refs: tuple[str, ...] = ()  # ids de personajes cuya hoja sirve de referencia
    ref_text: str = ""  # frase extra del prompt, solo si todas las referencias existen
    sheet: bool = False  # hoja de personaje (cuadrada); el resto son tomas con la proporción del video


def _who(script, ids) -> str:
    by_id = {c.id: c for c in script.characters}
    return " ".join(
        f"{by_id[i].name}: {by_id[i].visual}." for i in dict.fromkeys(ids) if i in by_id
    )


def _prompt(style: Style, *parts: str) -> str:
    return " ".join([style.style + ".", *[p.strip() for p in parts if p.strip()]])


def shot_key(scene_id: str, n: int) -> str:
    """Clave de la n-ésima toma (desde 1) de una escena; el montaje usa la misma."""
    return f"{scene_id}-{n}"


MAX_REFS = 4  # límite de FLUX.2 klein


def _refs(ids) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ids))[:MAX_REFS]


def _ref_text(script, ids: tuple[str, ...]) -> str:
    """Pide respetar el aspecto de la hoja pero cambiar la pose (la referencia tiende a copiarla)."""
    by_id = {c.id: c.name for c in script.characters}
    return " ".join(
        f"{by_id[cid]} looks exactly like reference image {i} (same colors, face and clothes) "
        "but in the new pose and action described, not the pose of the reference."
        for i, cid in enumerate(ids)
    )


def _sheets(script, style: Style) -> list[ImageRequest]:
    return [
        ImageRequest(
            f"personaje-{c.id}",
            _prompt(
                style,
                "Character design sheet, full body, neutral pose, plain background.",
                f"{c.name}: {c.visual}.",
            ),
            style.negative,
            sheet=True,
        )
        for c in script.characters
    ]


def plan_images(
    stage: str, script, style: Style, with_refs: bool = False
) -> list[ImageRequest]:
    expected = STAGES.get(stage)
    if expected is None or not isinstance(script, expected):
        raise ValueError(f"La etapa '{stage}' no aplica a un guion '{script.format}'.")
    neg = style.negative
    if stage == "characters":
        return _sheets(script, style)
    if stage == "visuals":
        out, seen = [], set()
        for i, shot in enumerate(script.body.shots, 1):
            refs = _refs(shot.characters) if with_refs else ()
            out.append(
                ImageRequest(
                    f"toma-{i}",
                    _prompt(style, shot.description, _who(script, shot.characters)),
                    neg,
                    shot.motion,
                    priority=shot.section_index not in seen,
                    refs=refs,
                    ref_text=_ref_text(script, refs),
                )
            )
            seen.add(shot.section_index)
        if (
            with_refs
        ):  # las rimas no tienen etapa `characters`: sus hojas se hacen aquí, primero
            used = {c for r in out for c in r.refs}
            sheets = [
                r
                for r in _sheets(script, style)
                if r.key.removeprefix("personaje-") in used
            ]
            out = sheets + out
        return out
    out = []
    for scene in script.body.scenes:
        # Guion antiguo (sin tomas): una sola desde las notas visuales.
        shots = scene.shots or [None]
        for n, shot in enumerate(shots, 1):
            start = shot.beat_index if shot else 0
            end = shots[n].beat_index if n < len(shots) else len(scene.beats)
            speakers = [
                b.speaker for b in scene.beats[start:end] if b.speaker != NARRATOR
            ]
            what = shot.description if shot else scene.visual_notes
            refs = _refs(speakers) if with_refs else ()
            out.append(
                ImageRequest(
                    shot_key(scene.id, n),
                    _prompt(
                        style,
                        what,
                        f"Setting: {scene.setting}.",
                        _who(script, speakers),
                    ),
                    neg,
                    shot.motion if shot else None,
                    priority=n == 1,
                    refs=refs,
                    ref_text=_ref_text(script, refs),
                )
            )
    return out
