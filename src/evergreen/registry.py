from evergreen.adapters.base import Adapter

# Etapas por formato; las implementaciones reales llegan con cada módulo.
STAGES = {
    "rhyme": ["script", "song", "visuals", "assembly"],
    "long": ["script", "voice", "music", "characters", "scenes", "assembly"],
}
# Archivos que se esperan en inbox/ cuando una etapa se hace a mano. Valores por
# defecto: cada módulo los afina al definir su etapa.
MANUAL_FILES = {
    "script": ["script.md"],
    "song": ["song.mp3"],
    "voice": ["voice.mp3"],
    "music": ["music.mp3"],
    "visuals": ["visuals.mp4"],
    "characters": ["characters.png"],
    "scenes": ["scenes.mp4"],
    "assembly": ["final.mp4"],
}
# Etapas tras las cuales se pide aprobación: `script` es gratis de revisar y evita
# gastar créditos de audio en un guion malo; el resto es donde más créditos se gastan.
REVIEW_GATES = {
    "rhyme": ["script", "song"],
    "long": ["script", "voice", "characters", "scenes"],
}
# nombre de etapa -> adaptador; los módulos siguientes registran aquí el suyo.
ADAPTERS: dict[str, Adapter] = {}
