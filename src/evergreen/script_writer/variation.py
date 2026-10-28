"""Variación entre videos: ejes elegidos con semilla y control de novedad en local."""

import random
import re
from collections.abc import Iterable
from itertools import product
from pathlib import Path

from evergreen.script_writer.models import (
    LongScript,
    RhymeScript,
    Variation,
    read_script,
)

# Estructuras y giros por formato: la rima habla de estrofas y estribillos; el video largo, de escenas.
AXES = {
    "rhyme": {
        "structures": [
            "acumulativa (cada estrofa suma un elemento)",
            "pregunta y respuesta",
            "cuenta regresiva",
            "un viaje con paradas",
            "llamada y respuesta",
            "descubrimiento de un objeto",
            "rutina de un día",
            "adivinanza que se resuelve al final",
        ],
        "twists": [
            "un eco que responde",
            "un personaje que se equivoca con gracia",
            "un sonido onomatopéyico que se repite",
            "un número que cambia en cada estrofa",
            "una sorpresa en la última estrofa",
            "un objeto misterioso que aparece al final",
            "un estribillo que cambia una palabra cada vez",
            "un invitado inesperado",
        ],
    },
    "long": {
        "structures": [
            "misión con obstáculos",
            "misterio por resolver",
            "un día que sale mal",
            "un viaje donde se aprende algo",
            "un problema que se resuelve en equipo",
            "una amistad que se pone a prueba",
            "un descubrimiento que cambia la rutina",
            "una competencia amistosa",
        ],
        "twists": [
            "un personaje que se equivoca con gracia",
            "una pista escondida desde la primera escena",
            "un invitado inesperado",
            "una sorpresa en la última escena",
            "un objeto misterioso que cambia de dueño",
            "un malentendido que se aclara al final",
            "un ayudante inesperado",
            "una frase que cada personaje repite a su manera",
        ],
    },
}
TONES = [  # comunes a los dos formatos
    "juguetón",
    "arrullo tranquilo",
    "enérgico",
    "curioso",
    "tierno",
    "divertido y exagerado",
]
SIMILARITY_THRESHOLD = 0.35  # estimación inicial; se afina con guiones reales
NGRAM = 3

Script = RhymeScript | LongScript


def pick_variation(
    fmt: str, seed: int | None = None, avoid: Iterable[Variation] = ()
) -> Variation:
    """Elige estructura, tono y giro del formato; evita combinaciones ya usadas mientras queden libres."""
    seed = random.SystemRandom().randrange(2**31) if seed is None else seed
    rng = random.Random(seed)
    axes = AXES[fmt]
    combos = list(product(axes["structures"], TONES))
    used = {(v.structure, v.tone) for v in avoid}
    structure, tone = rng.choice([c for c in combos if c not in used] or combos)
    return Variation(
        seed=seed, structure=structure, tone=tone, twist=rng.choice(axes["twists"])
    )


def existing_scripts(
    root: Path, exclude: str | None = None
) -> list[tuple[str, Script]]:
    """Guiones ya guardados en la carpeta de videos; los ilegibles se ignoran."""
    found = []
    for path in sorted(root.glob("*/stages/script/script.json")):
        video_id = path.parents[2].name
        if video_id == exclude:
            continue
        try:
            found.append((video_id, read_script(path)))
        except ValueError:  # JSON roto o contrato antiguo
            continue
    return found


def _units(script: Script) -> list[str]:
    if isinstance(script, RhymeScript):
        return [line for s in script.body.sections for line in s.lines]
    return [b.text for sc in script.body.scenes for b in sc.beats]


def _shingles(script: Script) -> set[tuple[str, ...]]:
    # Por línea o diálogo y en conjunto: un estribillo repetido no añade nada,
    # ni siquiera las uniones entre repeticiones.
    found: set[tuple[str, ...]] = set()
    for unit in _units(script):
        words = re.findall(r"\w+", unit.lower())
        n = min(NGRAM, len(words))
        found |= {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}
    return found


def similarity(a: Script, b: Script) -> float:
    """Jaccard de n-gramas de palabras: 1,0 idénticos, ~0 sin relación."""
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def find_similar(
    script: Script,
    others: Iterable[tuple[str, Script]],
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[str, float] | None:
    """El video más parecido con similitud >= umbral, o None."""
    scored = [(video_id, similarity(script, other)) for video_id, other in others]
    best = max(scored, key=lambda x: x[1], default=None)
    return best if best and best[1] >= threshold else None
