"""Agrupa los diálogos de cada escena en peticiones de a lo sumo 2 voces (límite de Gemini)."""

from dataclasses import dataclass

MAX_VOICES = 2


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    emotion: str


@dataclass(frozen=True)
class VoiceRequest:
    key: str  # nombre del archivo sin extensión: "escena-1" o "escena-1-2" si la escena se parte
    scene_id: str
    turns: tuple[Turn, ...]

    @property
    def speakers(self) -> list[str]:
        return list(dict.fromkeys(t.speaker for t in self.turns))


def plan_requests(scenes) -> list[VoiceRequest]:
    """Cortes contiguos y voraces: se conserva el orden y se usan las menos peticiones posibles."""
    out = []
    for scene in scenes:
        parts: list[list[Turn]] = []
        for beat in scene.beats:
            turn = Turn(beat.speaker, beat.text, beat.emotion)
            current = parts[-1] if parts else None
            if (
                current is None
                or turn.speaker not in {t.speaker for t in current}
                and len({t.speaker for t in current}) >= MAX_VOICES
            ):
                parts.append([])
            parts[-1].append(turn)
        for n, turns in enumerate(parts, 1):
            key = scene.id if len(parts) == 1 else f"{scene.id}-{n}"
            out.append(VoiceRequest(key, scene.id, tuple(turns)))
    return out
