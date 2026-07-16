"""Tests for tool file-glob discovery and gitignore defaults."""

from __future__ import annotations

from pathlib import Path

from pyossmtool.discovery import argv_targets_for_check, effective_file_globs
from pyossmtool.ignore import resolve_effective_ignores
from pyossmtool.models import (
    CheckDef,
    InstallMethod,
    InstallSpec,
    ProjectConfig,
    SuiteDef,
    ToolDef,
)


def _tool(files: list[str]) -> ToolDef:
    return ToolDef(
        id="demo",
        name="Demo",
        description="demo",
        install=InstallSpec(method=InstallMethod.SKIP),
        binary="true",
        files=files,
    )


def _check(*, include: list[str] | None = None) -> CheckDef:
    return CheckDef(
        id="demo.check",
        tool="demo",
        name="Demo",
        description="demo",
        parser="noop",
        include=include or [],
    )


def test_default_target_is_dot() -> None:
    config = ProjectConfig(suite="standard")
    assert config.target == "."
    suite = SuiteDef(id="s", name="S", description="s", checks=[])
    assert suite.target == "."


def test_always_loads_gitignore_even_when_suite_omits_profile(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("secret/\n", encoding="utf-8")
    suite = SuiteDef(id="s", name="S", description="s", checks=[])
    ignores = resolve_effective_ignores(tmp_path, suite=suite)
    assert ignores.is_ignored("secret/key.txt")
    assert not ignores.is_ignored("src/app.py")


def test_tool_files_expand_respects_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "skip.py").write_text("x = 1\n", encoding="utf-8")

    tool = _tool(["**/*.py"])
    check = _check()
    ignores = resolve_effective_ignores(tmp_path)
    targets = argv_targets_for_check(
        project_root=tmp_path,
        check=check,
        tool=tool,
        target=".",
        ignores=ignores,
    )
    assert targets is not None
    assert "keep.py" in targets or "./keep.py" in targets or any(t.endswith("keep.py") for t in targets)
    assert not any("skip.py" in t for t in targets)


def test_check_include_overrides_tool_files() -> None:
    tool = _tool(["**/*.py"])
    check = _check(include=["**/*.md"])
    assert effective_file_globs(check, tool) == ["**/*.md"]


def test_empty_files_passes_directory_target() -> None:
    tool = _tool([])
    check = _check()
    targets = argv_targets_for_check(
        project_root=Path("/tmp"),
        check=check,
        tool=tool,
        target=".",
        ignores=None,
    )
    assert targets == ["."]
