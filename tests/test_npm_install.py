"""Tests for project-local npm installs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pyossmtool.installer import Installer
from pyossmtool.models import InstallMethod, InstallSpec, ToolDef
from pyossmtool.registry import Registry
from pyossmtool.resolver import BinaryResolver


def test_npm_install_uses_project_prefix(tmp_path: Path) -> None:
    registry = Registry(project_root=tmp_path)
    installer = Installer(registry, tmp_path)
    tool = ToolDef(
        id="jscpd",
        name="JSCPD",
        description="demo",
        install=InstallSpec(method=InstallMethod.NPM, package="jscpd"),
        binary="jscpd",
    )
    with patch("pyossmtool.installer.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        installer._install_npm(tool)
    assert run.called
    argv = run.call_args.args[0]
    assert argv[:3] == ["npm", "install", "--no-save"]
    assert "--prefix" in argv
    prefix = Path(argv[argv.index("--prefix") + 1])
    assert prefix == tmp_path / ".pyossmtool" / "tools" / "npm"
    assert "jscpd" in argv
    assert "-g" not in argv
    assert (tmp_path / ".pyossmtool" / "tools" / "npm" / "package.json").exists()


def test_resolver_finds_managed_npm_binary(tmp_path: Path) -> None:
    bin_dir = tmp_path / ".pyossmtool" / "tools" / "npm" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "jscpd"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    resolver = BinaryResolver(tmp_path)
    tool = ToolDef(
        id="jscpd",
        name="JSCPD",
        description="demo",
        install=InstallSpec(method=InstallMethod.NPM, package="jscpd"),
        binary="jscpd",
    )
    assert resolver._resolve_npm("jscpd") == binary
    assert resolver._resolve_managed(tool) == binary
