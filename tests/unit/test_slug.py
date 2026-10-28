import pytest

from evergreen.errors import EvergreenError
from evergreen.slug import slugify


def test_accents_and_enye():
    assert slugify("El ñandú canción") == "el-nandu-cancion"


def test_symbols_are_collapsed():
    assert slugify("  ¡Los patitos! / (v2) ") == "los-patitos-v2"


@pytest.mark.parametrize("bad", ["", "   ", "!!!", "日本語"])
def test_unusable_title_rejected(bad):
    with pytest.raises(EvergreenError):
        slugify(bad)
