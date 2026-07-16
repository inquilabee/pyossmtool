"""Tests for declarative tool config and single-target resolution."""

from __future__ import annotations

from pathlib import Path

from pyossmtool.config_resolver import ConfigResolver
from pyossmtool.models import (
    CheckDef,
    ConfigMode,
    ConfigSpec,
    InstallMethod,
    InstallSpec,
    ProjectConfig,
    SuiteCheckRef,
    SuiteDef,
    ToolConfigSpec,
    ToolDef,
)
from pyossmtool.registry import Registry
from pyossmtool.target_expand import (
    expand_include_globs,
    format_check_argv,
    resolve_suite_target,
)


def _tool(*, config: ToolConfigSpec | None = None, tool_id: str = "demo") -> ToolDef:
    return ToolDef(
        id=tool_id,
        name="Demo",
        description="demo",
        install=InstallSpec(method=InstallMethod.SKIP),
        binary="true",
        config=config,
    )


def _defaults_dir() -> Path:
    from pyossmtool.registry import BUNDLE_ROOT

    return BUNDLE_ROOT / "defaults" / "configs"


def test_config_auto_uses_bundled_when_repo_has_none(tmp_path: Path) -> None:
    tool = _tool(config=ToolConfigSpec(flag="--config", bundled="ruff.toml", repo_files=["ruff.toml"]))
    resolver = ConfigResolver(tmp_path)
    resolver.defaults_dir = _defaults_dir()
    path = resolver.resolve_config_path(tool, None)
    assert path is not None
    assert path.name == "ruff.toml"
    assert resolver.extra_argv(tool, None) == ["--config", str(path)]


def test_config_auto_skips_when_repo_file_present(tmp_path: Path) -> None:
    (tmp_path / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
    tool = _tool(config=ToolConfigSpec(flag="--config", bundled="ruff.toml", repo_files=["ruff.toml"]))
    resolver = ConfigResolver(tmp_path)
    assert resolver.resolve_config_path(tool, None) is None
    assert resolver.extra_argv(tool, None) == []


def test_config_pass_flag_false(tmp_path: Path) -> None:
    tool = _tool(
        config=ToolConfigSpec(
            flag="-c",
            bundled="markdownlint.json",
            pass_flag=False,
            repo_files=[".markdownlint.json"],
        )
    )
    resolver = ConfigResolver(tmp_path)
    resolver.defaults_dir = _defaults_dir()
    path = resolver.resolve_config_path(tool, None)
    assert path is not None
    assert resolver.extra_argv(tool, None) == []


def test_config_paths_mode(tmp_path: Path) -> None:
    custom = tmp_path / "custom.toml"
    custom.write_text("x = 1\n", encoding="utf-8")
    tool = _tool(config=ToolConfigSpec(flag="--config", bundled="ruff.toml"))
    project = ProjectConfig(
        suite="demo",
        configs=ConfigSpec(mode=ConfigMode.PATHS, paths={"demo": "custom.toml"}),
    )
    resolver = ConfigResolver(tmp_path)
    assert resolver.resolve_config_path(tool, project) == custom.resolve()
    assert resolver.extra_argv(tool, project) == ["--config", str(custom.resolve())]


def test_bandit_use_pyproject_as_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.bandit]\nskips = []\n", encoding="utf-8")
    tool = _tool(
        config=ToolConfigSpec(
            flag="-c",
            bundled="bandit.yaml",
            pyproject=["tool", "bandit"],
            use_pyproject_as_path=True,
        )
    )
    resolver = ConfigResolver(tmp_path)
    path = resolver.resolve_config_path(tool, None)
    assert path == (tmp_path / "pyproject.toml").resolve()
    assert resolver.extra_argv(tool, None)[0] == "-c"


def test_expand_include_braces(tmp_path: Path) -> None:
    (tmp_path / "a.sh").write_text("echo hi\n", encoding="utf-8")
    (tmp_path / "b.bash").write_text("echo hi\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("x = 1\n", encoding="utf-8")
    matches = expand_include_globs(tmp_path, ["**/*.{sh,bash}"])
    assert matches == ["a.sh", "b.bash"]


def test_format_check_argv_expands_target_slot() -> None:
    assert format_check_argv(
        ["-f", "json", "{target}"],
        ["a.sh", "b.sh"],
        {"cov": "src/"},
    ) == ["-f", "json", "a.sh", "b.sh"]


def test_resolve_target_prefers_project_for_configured_suite() -> None:
    suite = SuiteDef(
        id="python-quality",
        name="PQ",
        description="d",
        checks=[SuiteCheckRef(id="ruff.lint")],
        target="src/",
    )
    project = ProjectConfig(suite="python-quality", target="src/")
    assert resolve_suite_target(SuiteCheckRef(id="ruff.lint"), suite, project) == "src/"


def test_resolve_target_uses_suite_when_not_project_suite() -> None:
    suite = SuiteDef(
        id="formatting",
        name="F",
        description="d",
        checks=[SuiteCheckRef(id="ruff.format")],
        target=".",
    )
    project = ProjectConfig(suite="python-quality", target="src/")
    assert resolve_suite_target(SuiteCheckRef(id="ruff.format"), suite, project) == "."


def test_catalog_tools_load_with_config() -> None:
    registry = Registry()
    assert registry.get_tool("yamlfmt").config is not None
    assert registry.get_tool("yamlfmt").config.flag == "-conf"
    assert registry.get_tool("ruff").config.pyproject == ["tool", "ruff"]
    check = registry.get_check("shellcheck")
    assert check.include
    assert "target_key" not in CheckDef.model_fields
