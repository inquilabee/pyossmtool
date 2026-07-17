"""Tests for Tool docs version resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from shipgate.models import InstallMethod, InstallSpec, ToolDef
from shipgate.server.tool_versions import (
    _normalize_version_line,
    _parse_version_from_output,
    tool_docs_rows,
)


def _tool(*, package: str | None = "ruff>=0.15.0", binary: str = "ruff") -> ToolDef:
    return ToolDef(
        id="ruff",
        name="Ruff",
        description="Fast Python linter",
        install=InstallSpec(method=InstallMethod.PIP, package=package),
        binary=binary,
        documentation_url="https://docs.astral.sh/ruff/",
    )


def test_normalize_version_strips_binary_name() -> None:
    assert _normalize_version_line("ruff 0.15.22", "ruff") == "0.15.22"
    assert _normalize_version_line("mdformat 1.0.0", "mdformat") == "1.0.0"


def test_parse_version_from_output_handles_shellcheck_and_mutmut() -> None:
    shellcheck = "ShellCheck - shell script analysis tool\nversion: 0.11.0\nlicense: GNU GPL"
    assert _parse_version_from_output(shellcheck, "shellcheck") == "0.11.0"
    assert _parse_version_from_output("mutmut, version 3.6.0", "mutmut") == "3.6.0"
    assert _parse_version_from_output("Dockerfile Linter 2.14.0", "hadolint") == "2.14.0"


def test_parse_version_from_output_rejects_binary_name_only() -> None:
    assert _parse_version_from_output("yamlfmt", "yamlfmt") is None
    assert _parse_version_from_output("version is set by build process", "gitleaks") is None


def test_tool_docs_rows_prefer_installed_version(tmp_path: Path) -> None:
    tool = _tool()
    resolver = MagicMock()
    resolver.resolve.return_value = tmp_path / "ruff"
    completed = MagicMock(stdout="ruff 0.15.22\n", stderr="")
    with (
        patch("shipgate.server.tool_versions.BinaryResolver", return_value=resolver),
        patch("shipgate.server.tool_versions.subprocess.run", return_value=completed),
    ):
        rows = tool_docs_rows([tool], tmp_path)
    assert rows[0].version == "0.15.22"


def test_tool_docs_rows_fall_back_to_package_constraint(tmp_path: Path) -> None:
    tool = _tool(package="bandit>=1.8.0")
    resolver = MagicMock()
    resolver.resolve.side_effect = FileNotFoundError("missing")
    with patch("shipgate.server.tool_versions.BinaryResolver", return_value=resolver):
        rows = tool_docs_rows([tool], tmp_path)
    assert rows[0].version == "bandit>=1.8.0"


def test_tool_docs_rows_use_em_dash_when_version_unknown(tmp_path: Path) -> None:
    tool = ToolDef(
        id="gitleaks",
        name="Gitleaks",
        description="secrets",
        install=InstallSpec(method=InstallMethod.SYSTEM, package="gitleaks"),
        binary="gitleaks",
    )
    resolver = MagicMock()
    resolver.resolve.side_effect = FileNotFoundError("missing")
    with patch("shipgate.server.tool_versions.BinaryResolver", return_value=resolver):
        rows = tool_docs_rows([tool], tmp_path)
    assert rows[0].version == "—"
