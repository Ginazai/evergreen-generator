import re
import unicodedata

from evergreen.errors import EvergreenError


def slugify(title: str) -> str:
    """ASCII seguro para nombres de carpeta en Windows: 'El ñandú' -> 'el-nandu'."""
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-")
    if not slug:
        raise EvergreenError(
            f"El título '{title}' no genera un nombre de carpeta válido."
        )
    return slug
