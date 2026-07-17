from pathlib import Path

import pytest

from shipgate.models import EnvMode, InstallMethod, InstallSpec, ToolDef
from shipgate.resolver import BinaryResolver


def test_resolver_uses_tools_root_not_analysis_root(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()
    bin_dir = primary / ".shipgate" / "tools" / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "ruff"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    tool = ToolDef(
        id="ruff",
        name="Ruff",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="ruff"),
        binary="ruff",
    )
    resolver = BinaryResolver(project_root=worktree, tools_root=primary)
    assert resolver.resolve(tool, EnvMode.MANAGED) == binary.resolve()


def test_resolver_project_mode_prefers_primary_venv_over_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()

    managed_bin = primary / ".shipgate" / "tools" / "venv" / "bin"
    managed_bin.mkdir(parents=True)
    managed_pytest = managed_bin / "pytest"
    managed_pytest.write_text("#!/bin/sh\necho managed\n", encoding="utf-8")
    managed_pytest.chmod(0o755)

    project_bin = primary / ".venv" / "bin"
    project_bin.mkdir(parents=True)
    project_pytest = project_bin / "pytest"
    project_pytest.write_text("#!/bin/sh\necho project\n", encoding="utf-8")
    project_pytest.chmod(0o755)

    # Ignore the real test-runner env so conventional .venv wins in this unit test.
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("shipgate.resolver.sys.executable", str(tmp_path / "no-env" / "python"))

    tool = ToolDef(
        id="pytest",
        name="pytest",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="pytest"),
        binary="pytest",
    )
    resolver = BinaryResolver(project_root=worktree, tools_root=primary)
    assert resolver.resolve(tool, EnvMode.PROJECT) == project_pytest.resolve()
    assert resolver.resolve(tool, EnvMode.MANAGED) == managed_pytest.resolve()


def test_resolver_project_mode_uses_virtual_env_any_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()

    managed_bin = primary / ".shipgate" / "tools" / "venv" / "bin"
    managed_bin.mkdir(parents=True)
    managed_pytest = managed_bin / "pytest"
    managed_pytest.write_text("#!/bin/sh\necho managed\n", encoding="utf-8")
    managed_pytest.chmod(0o755)

    custom_env = primary / "my-project-env"
    custom_bin = custom_env / "bin"
    custom_bin.mkdir(parents=True)
    custom_pytest = custom_bin / "pytest"
    custom_pytest.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
    custom_pytest.chmod(0o755)
    monkeypatch.setenv("VIRTUAL_ENV", str(custom_env))

    tool = ToolDef(
        id="pytest",
        name="pytest",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="pytest"),
        binary="pytest",
    )
    resolver = BinaryResolver(project_root=worktree, tools_root=primary)
    assert resolver.resolve(tool, EnvMode.PROJECT) == custom_pytest.resolve()


def test_resolver_project_mode_uses_running_interpreter_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    worktree = tmp_path / "worktree"
    primary.mkdir()
    worktree.mkdir()

    managed_bin = primary / ".shipgate" / "tools" / "venv" / "bin"
    managed_bin.mkdir(parents=True)
    (managed_bin / "pytest").write_text("#!/bin/sh\necho managed\n", encoding="utf-8")
    (managed_bin / "pytest").chmod(0o755)

    custom_bin = primary / "conda-env" / "bin"
    custom_bin.mkdir(parents=True)
    custom_python = custom_bin / "python"
    custom_python.write_text("#!/bin/sh\n", encoding="utf-8")
    custom_python.chmod(0o755)
    custom_pytest = custom_bin / "pytest"
    custom_pytest.write_text("#!/bin/sh\necho interpreter\n", encoding="utf-8")
    custom_pytest.chmod(0o755)

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("shipgate.resolver.sys.executable", str(custom_python))

    tool = ToolDef(
        id="pytest",
        name="pytest",
        description="x",
        install=InstallSpec(method=InstallMethod.PIP, package="pytest"),
        binary="pytest",
    )
    resolver = BinaryResolver(project_root=worktree, tools_root=primary)
    assert resolver.resolve(tool, EnvMode.PROJECT) == custom_pytest.resolve()
