"""CLI identity tests."""

from __future__ import annotations

from typer.testing import CliRunner

from pyossmtool.cli import app


def test_cli_entry_name() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Quality-gate orchestrator" in result.output
    assert "check" in result.output
    assert "format" in result.output
    assert "list" in result.output
    assert "install" in result.output
