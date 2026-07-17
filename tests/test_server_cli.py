import re

from typer.testing import CliRunner

from shipgate.cli import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_server_help() -> None:
    result = CliRunner().invoke(app, ["server", "--help"])
    assert result.exit_code == 0
    text = _ANSI_RE.sub("", result.stdout or result.output or "")
    assert "--port" in text
