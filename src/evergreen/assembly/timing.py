"""Cuánto dura cada toma. Funciones puras: el reparto es proporcional al texto o a las líneas."""

from dataclasses import dataclass

from evergreen.script_writer.models import LongScript, RhymeScript
from evergreen.visuals.prompts import shot_key

MIN_SHOT = 1.0  # una toma más corta que esto no se ve


@dataclass(frozen=True)
class ShotSpan:
    key: str  # clave de la imagen (la misma que usa la etapa de imágenes)
    scene_id: str  # escena (long) o sección (rhyme) a la que pertenece
    seconds: float


def _chars(beats) -> int:
    return max(1, sum(len(b.text) for b in beats))


def scene_seconds_from_total(script: LongScript, total: float) -> dict[str, float]:
    """Voz manual (un solo archivo): se reparte el total entre escenas según su texto."""
    weights = {s.id: _chars(s.beats) for s in script.body.scenes}
    whole = sum(weights.values())
    return {sid: total * w / whole for sid, w in weights.items()}


def long_spans(script: LongScript, scene_seconds: dict[str, float]) -> list[ShotSpan]:
    out = []
    for scene in script.body.scenes:
        shots = scene.shots or [None]  # guion antiguo: una sola toma por escena
        weights = []
        for n, shot in enumerate(shots):
            start = shot.beat_index if shot else 0
            end = shots[n + 1].beat_index if n + 1 < len(shots) else len(scene.beats)
            weights.append(_chars(scene.beats[start:end]))
        total = scene_seconds[scene.id]
        out += [
            ShotSpan(shot_key(scene.id, n), scene.id, total * w / sum(weights))
            for n, w in enumerate(weights, 1)
        ]
    return out


def rhyme_spans(script: RhymeScript, total: float) -> list[ShotSpan]:
    """La canción se reparte por secciones según sus líneas; las tomas de una sección se la dividen."""
    sections = script.body.sections
    per_section: dict[int, int] = {}
    for shot in script.body.shots:
        per_section[shot.section_index] = per_section.get(shot.section_index, 0) + 1
    raw = [
        (
            f"toma-{i}",
            f"seccion-{shot.section_index + 1}",
            len(sections[shot.section_index].lines) / per_section[shot.section_index],
        )
        for i, shot in enumerate(script.body.shots, 1)
    ]
    # Las secciones sin tomas no se muestran: su tiempo se reparte entre las demás.
    whole = sum(w for _, _, w in raw)
    return [ShotSpan(key, sid, total * w / whole) for key, sid, w in raw]
