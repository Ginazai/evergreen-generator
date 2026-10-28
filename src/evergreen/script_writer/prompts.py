"""Prompt de guion: una plantilla en español; el idioma de salida es un parámetro."""

import json

from evergreen.manifest import Format, Manifest
from evergreen.script_writer.models import LONG_SCENES, RHYME_LINES, Variation

LANGUAGE_NAME = {"es": "español", "en": "inglés"}


def example_data(fmt: Format, manifest: Manifest, variation: Variation) -> dict:
    """Esqueleto del JSON esperado. Una prueba comprueba que sigue el contrato."""
    character = {
        "id": "personaje-1",
        "name": "<nombre>",
        "visual": "<descripción visual en una frase, lista para un generador de imágenes>",
        "voice": "<cómo suena: edad, tono, ritmo>",
    }
    head = {
        "schema_version": 1,
        "format": fmt.value,
        "language": manifest.language.value,
        "title": manifest.title,
        "variation": variation.model_dump(),
        "characters": [character],
    }
    if fmt == Format.rhyme:
        body = {
            "style_prompt": "<estilo musical: ritmo, instrumentos y ánimo, sin nombrar artistas>",
            "bpm_hint": 100,
            "sections": [
                {"kind": "verse | chorus | bridge", "lines": ["<línea>", "<línea>"]}
            ],
            "shots": [
                {
                    "section_index": 0,
                    "description": "<qué se ve en pantalla>",
                    "characters": ["personaje-1"],
                    "motion": "<movimiento de cámara o acción, una frase>",
                }
            ],
        }
    else:
        body = {
            "logline": "<resumen en una frase>",
            "scenes": [
                {
                    "id": "escena-1",
                    "setting": "<dónde ocurre>",
                    "beats": [
                        {
                            "speaker": "personaje-1 | narrator",
                            "text": "<diálogo>",
                            "emotion": "<emoción>",
                        }
                    ],
                    "visual_notes": "<notas visuales>",
                    "shots": [
                        {
                            "beat_index": 0,
                            "description": "<qué se ve en pantalla, sin texto>",
                            "motion": "<movimiento de cámara o acción, una frase>",
                        }
                    ],
                }
            ],
        }
    return {**head, "body": body}


def _task(fmt: Format, language: str) -> str:
    if fmt == Format.rhyme:
        low, high = RHYME_LINES
        return (
            "Escribe la letra de una canción infantil (rima) para un video corto.\n"
            f"- Duración objetivo: de 30 segundos a 3 minutos cantados ({low} a {high} líneas en total).\n"
            f"- Las líneas deben rimar en {language}. Usa estribillo.\n"
            "- `style_prompt` describe la música para generar la canción (ritmo, instrumentos, ánimo); "
            "no nombres artistas ni canciones.\n"
            "- `shots` describe qué se ve en pantalla: al menos una toma por sección, con "
            "`section_index` empezando en 0; cada toma lleva `motion`, una frase de movimiento "
            "de cámara o acción para animar la imagen."
        )
    low, high = LONG_SCENES
    return (
        "Escribe el guion de un video largo con personajes y diálogo.\n"
        f"- Duración objetivo: de 5 a 10 minutos hablados ({low} a {high} escenas).\n"
        "- Longitud: entre 800 y 1500 palabras en total entre todos los diálogos (unas 150 por minuto).\n"
        "- Cada diálogo (`beats`) lo dice un personaje (usa su `id`) o `narrator`.\n"
        "- Cada escena tiene un `id` único y notas visuales.\n"
        "- Cada escena lleva de 2 a 5 `shots` (tomas): `beat_index` es el diálogo (desde 0) en que "
        "empieza la toma; la primera usa 0 y van en orden creciente, una toma cada 10 a 20 segundos "
        "de diálogo aproximadamente. `description` dice qué se ve (sin texto en pantalla) y `motion` "
        "es una frase de movimiento de cámara o acción para animar la imagen."
    )


def _cast_rules(cast) -> str:
    if not cast:
        return "- Crea entre 1 y 4 personajes; cada `id` va en minúsculas, sin espacios (puede llevar guiones).\n"
    listed = "\n".join(f"  - `{c.id}`: {c.name}, {c.visual} ({c.voice})" for c in cast)
    return (
        "- Usa SOLO estos personajes (entre 1 y 4), con su `id`, nombre, `visual` y `voice` tal cual:\n"
        f"{listed}\n"
    )


def build_prompt(manifest: Manifest, variation: Variation, cast=None) -> str:
    fmt = manifest.format
    language = LANGUAGE_NAME[manifest.language.value]
    brief = f"Tema o notas del autor: {manifest.brief}\n" if manifest.brief else ""
    example = json.dumps(
        example_data(fmt, manifest, variation), ensure_ascii=False, indent=2
    )
    return (
        f"Eres guionista de contenido infantil.\n\n"
        f"Título: {manifest.title}\n{brief}"
        f"Idioma de todo el contenido del guion: {language}.\n\n"
        f"{_task(fmt, language)}\n\n"
        "Variación obligatoria (para que este video no se parezca a los demás):\n"
        f"- Estructura: {variation.structure}\n"
        f"- Tono: {variation.tone}\n"
        f"- Elemento distintivo: {variation.twist}\n\n"
        "Reglas:\n"
        "- Contenido original: no copies canciones, personajes, series ni marcas existentes y no "
        "menciones marcas.\n"
        "- Apto para niños pequeños: sin violencia ni miedo intenso.\n"
        f"{_cast_rules(cast)}"
        "- Copia la `variation` exactamente como aparece abajo.\n\n"
        "Responde SOLO con un objeto JSON válido, sin texto antes ni después, con esta estructura "
        "(reemplaza lo que va entre <>):\n\n"
        f"{example}\n"
    )
