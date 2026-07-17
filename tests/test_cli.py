"""CLI identity and suite-default tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from shipgate.cli import app


def test_cli_entry_name() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Quality-gate orchestrator" in result.output
    assert "check" in result.output
    assert "format" in result.output
    assert "list" in result.output
    assert "install" in result.output


def test_install_requires_suite_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 2
    assert "suite:" in result.output or "--suite" in result.output


def test_install_uses_suite_from_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: python-quality\n", encoding="utf-8")
    with patch("shipgate.cli.Installer") as installer_cls:
        installer = MagicMock()
        installer_cls.return_value = installer
        result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 0
    installer.install_suite.assert_called_once_with("python-quality")


def test_install_suite_flag_overrides_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: python-quality\n", encoding="utf-8")
    with patch("shipgate.cli.Installer") as installer_cls:
        installer = MagicMock()
        installer_cls.return_value = installer
        result = CliRunner().invoke(app, ["install", "--suite", "format"])
    assert result.exit_code == 0
    installer.install_suite.assert_called_once_with("format")
