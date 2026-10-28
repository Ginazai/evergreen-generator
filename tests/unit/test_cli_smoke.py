from typer.testing import CliRunner

from evergreen import __version__
from evergreen.cli import app


def test_version_prints_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__
