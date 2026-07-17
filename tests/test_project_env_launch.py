"""Tests for PROJECT-mode launch rebinding to the project interpreter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shipgate.ignore import EffectiveIgnores
from shipgate.models import CheckDef, CheckMode, EnvMode, InstallMethod, InstallSpec, ToolDef
from shipgate.runner import Runner


def test_project_mode_rebinds_managed_mutmut_to_project_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    (worktree / "src").mkdir()

    project_bin = primary / ".venv" / "bin"
    project_bin.mkdir(parents=True)
    project_python = project_bin / "python"
    project_python.write_text("#!/bin/sh\n", encoding="utf-8")
    project_python.chmod(0o755)

    managed_bin = primary / ".shipgate" / "tools" / "venv" / "bin"
    managed_bin.mkdir(parents=True)
    managed_mutmut = managed_bin / "mutmut"
    managed_mutmut.write_text("#!/bin/sh\n", encoding="utf-8")
    managed_mutmut.chmod(0o755)
    site = primary / ".shipgate" / "tools" / "venv" / "lib" / "python3.13" / "site-packages"
    site.mkdir(parents=True)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("shipgate.resolver.sys.executable", str(tmp_path / "no-env" / "python"))

    runner = Runner(MagicMock(), project_root=worktree, tools_root=primary)
    tool = ToolDef(
        id="mutmut",
        name="mutmut",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="mutmut"),
        binary="mutmut",
    )
    check = CheckDef(
        id="mutmut.run",
        tool="mutmut",
        name="mutmut",
        description="x",
        parser="mutmut_text",
        mode=CheckMode.CHECK,
        argv=["run"],
    )
    argv, env = runner._build_native_argv(
        check,
        "mutmut.run",
        [],
        tool,
        EnvMode.PROJECT,
        None,
        effective_ignores=EffectiveIgnores(profile_files=[], path_patterns=[]),
    )
    assert argv[:3] == [str(project_python), "-m", "mutmut"]
    assert argv[3:] == ["run"]
    pythonpath = env["PYTHONPATH"].split(":")
    assert pythonpath[0] == str(worktree / "src")
    assert str(site) in pythonpath


def test_auto_mode_rebinds_managed_mutmut_to_project_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """env: auto should still run mutmut via project python when only managed has the binary."""
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    (worktree / "src").mkdir()

    project_bin = primary / ".venv" / "bin"
    project_bin.mkdir(parents=True)
    project_python = project_bin / "python"
    project_python.write_text("#!/bin/sh\n", encoding="utf-8")
    project_python.chmod(0o755)

    managed_bin = primary / ".shipgate" / "tools" / "venv" / "bin"
    managed_bin.mkdir(parents=True)
    managed_mutmut = managed_bin / "mutmut"
    managed_mutmut.write_text("#!/bin/sh\n", encoding="utf-8")
    managed_mutmut.chmod(0o755)
    site = primary / ".shipgate" / "tools" / "venv" / "lib" / "python3.13" / "site-packages"
    site.mkdir(parents=True)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("shipgate.resolver.sys.executable", str(tmp_path / "no-env" / "python"))

    runner = Runner(MagicMock(), project_root=worktree, tools_root=primary)
    tool = ToolDef(
        id="mutmut",
        name="mutmut",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="mutmut"),
        binary="mutmut",
    )
    check = CheckDef(
        id="mutmut.run",
        tool="mutmut",
        name="mutmut",
        description="x",
        parser="mutmut_text",
        mode=CheckMode.CHECK,
        argv=["run"],
    )
    argv, env = runner._build_native_argv(
        check,
        "mutmut.run",
        [],
        tool,
        EnvMode.AUTO,
        None,
        effective_ignores=EffectiveIgnores(profile_files=[], path_patterns=[]),
    )
    assert argv[:3] == [str(project_python), "-m", "mutmut"]
    assert str(worktree / "src") in env["PYTHONPATH"]


def test_project_mode_keeps_project_pytest_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    (worktree / "src").mkdir()

    project_bin = primary / ".venv" / "bin"
    project_bin.mkdir(parents=True)
    project_python = project_bin / "python"
    project_python.write_text("#!/bin/sh\n", encoding="utf-8")
    project_python.chmod(0o755)
    project_pytest = project_bin / "pytest"
    project_pytest.write_text("#!/bin/sh\n", encoding="utf-8")
    project_pytest.chmod(0o755)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("shipgate.resolver.sys.executable", str(tmp_path / "no-env" / "python"))

    runner = Runner(MagicMock(), project_root=worktree, tools_root=primary)
    tool = ToolDef(
        id="pytest",
        name="pytest",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="pytest"),
        binary="pytest",
    )
    check = CheckDef(
        id="pytest.test",
        tool="pytest",
        name="pytest",
        description="x",
        parser="pytest_text",
        mode=CheckMode.CHECK,
        argv=["{target}", "-q"],
    )
    argv, env = runner._build_native_argv(
        check,
        "pytest.test",
        ["tests/"],
        tool,
        EnvMode.PROJECT,
        None,
        effective_ignores=EffectiveIgnores(profile_files=[], path_patterns=[]),
    )
    assert argv[0] == str(project_pytest)
    assert "-m" not in argv
    assert str(worktree / "src") in env["PYTHONPATH"]
