"""Guiones de ejemplo válidos, compartidos por las pruebas de script-writer."""

VARIATION = {
    "seed": 1,
    "structure": "acumulativa",
    "tone": "juguetón",
    "twist": "un eco que responde",
}
CHARACTERS = [
    {
        "id": "lola",
        "name": "Lola",
        "visual": "patita amarilla con botas rojas",
        "voice": "aguda y alegre",
    },
    {
        "id": "pipo",
        "name": "Pipo",
        "visual": "pato azul con gorra",
        "voice": "grave y tranquilo",
    },
]


def rhyme_data(language="es"):
    section = {"kind": "verse", "lines": ["uno", "dos", "tres", "cuatro"]}
    return {
        "schema_version": 1,
        "format": "rhyme",
        "language": language,
        "title": "Los patitos",
        "variation": dict(VARIATION),
        "characters": [dict(c) for c in CHARACTERS],
        "body": {
            "style_prompt": "folk infantil alegre, ukelele y palmas",
            "bpm_hint": 100,
            "sections": [
                section,
                {"kind": "chorus", "lines": ["a", "b", "c", "d"]},
                section,
            ],
            "shots": [
                {
                    "section_index": 0,
                    "description": "Lola nada en el estanque",
                    "characters": ["lola"],
                    "motion": "zoom lento hacia Lola",
                }
            ],
        },
    }


def long_data(language="es"):
    beat = {"speaker": "lola", "text": "¡Hola!", "emotion": "alegre"}
    scene = lambda n: {
        "id": f"escena-{n}",
        "setting": "el estanque",
        "beats": [
            beat,
            {"speaker": "narrator", "text": "Y así siguió.", "emotion": "calmado"},
        ],
        "visual_notes": "luz de mañana",
        "shots": [
            {
                "beat_index": 0,
                "description": "Lola en la orilla",
                "motion": "zoom lento",
            },
            {
                "beat_index": 1,
                "description": "el estanque al amanecer",
                "motion": "paneo",
            },
        ],
    }
    return {
        "schema_version": 1,
        "format": "long",
        "language": language,
        "title": "Aventura en el estanque",
        "variation": dict(VARIATION),
        "characters": [dict(c) for c in CHARACTERS],
        "body": {
            "logline": "Lola descubre el eco.",
            "scenes": [scene(n) for n in range(1, 5)],
        },
    }
