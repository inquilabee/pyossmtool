"""Tests for declarative tool config and single-target resolution."""

from __future__ import annotations

from pathlib import Path

from shipgate.config_resolver import ConfigResolver
from shipgate.models import (
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
from shipgate.registry import Registry
from shipgate.target_expand import (
    drop_empty_flag_pairs,
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
    from shipgate.registry import BUNDLE_ROOT

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


def test_drop_empty_flag_pairs_removes_orphan_config() -> None:
    assert drop_empty_flag_pairs(["scan", "--config", "auto", "--config", "", "--json"]) == [
        "scan",
        "--config",
        "auto",
        "--json",
    ]


def test_config_pass_flag_false_uses_repo_dir_for_placeholder(tmp_path: Path) -> None:
    repo_rules = tmp_path / ".semgrep"
    repo_rules.mkdir()
    (repo_rules / "local.yml").write_text("rules: []\n", encoding="utf-8")
    tool = _tool(
        config=ToolConfigSpec(
            flag="--config",
            bundled_path="defaults/semgrep/python-quality.yml",
            pass_flag=False,
            repo_dirs=[".semgrep"],
        )
    )
    resolver = ConfigResolver(tmp_path)
    path = resolver.resolve_config_path(tool, None)
    assert path == (tmp_path / ".semgrep").resolve()


def test_semgrep_scan_argv_includes_builtin_rulesets(tmp_path: Path) -> None:
    check = Registry().get_check("semgrep.scan")
    tool = Registry().get_tool("semgrep")
    bundled = ConfigResolver(tmp_path).resolve_config_path(tool, None)
    assert bundled is not None
    argv = format_check_argv(
        check.argv,
        ["src/"],
        {"config": str(bundled), "cov": "src/"},
    )
    assert argv[:10] == [
        "scan",
        "--config",
        "p/ci",
        "--config",
        "p/secrets",
        "--config",
        "p/python",
        "--config",
        "r/bash",
        "--config",
    ]
    assert "auto" not in argv
    assert str(bundled) in argv
    assert "src/" in argv
    assert "--metrics" in argv
    assert argv[argv.index("--metrics") + 1] == "off"


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
    yamlfmt_config = registry.get_tool("yamlfmt").config
    assert yamlfmt_config is not None
    assert yamlfmt_config.flag == "-conf"
    ruff_config = registry.get_tool("ruff").config
    assert ruff_config is not None
    assert ruff_config.pyproject == ["tool", "ruff"]
    assert registry.get_tool("shellcheck").files
    assert registry.get_tool("ruff").files == ["**/*.py"]
    assert "target_key" not in CheckDef.model_fields


def test_config_convention_tool_yaml_at_repo_root(tmp_path: Path) -> None:
    (tmp_path / "demo.yaml").write_text("key: value\n", encoding="utf-8")
    tool = _tool(
        config=ToolConfigSpec(flag="--config", bundled="bandit.yaml"),
        tool_id="demo",
    )
    resolver = ConfigResolver(tmp_path)
    path = resolver.resolve_config_path(tool, None)
    assert path == (tmp_path / "demo.yaml").resolve()


def test_config_convention_tool_yaml_under_shipgate_configs(tmp_path: Path) -> None:
    config_dir = tmp_path / ".shipgate" / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "demo.yaml").write_text("key: value\n", encoding="utf-8")
    tool = _tool(
        config=ToolConfigSpec(flag="--config", bundled="bandit.yaml"),
        tool_id="demo",
    )
    resolver = ConfigResolver(tmp_path)
    path = resolver.resolve_config_path(tool, None)
    assert path == (config_dir / "demo.yaml").resolve()


def test_shellcheck_check_alias_resolves() -> None:
    registry = Registry()
    assert registry.get_check("shellcheck").id == "shellcheck.check"
    assert registry.get_check("shellcheck.check").id == "shellcheck.check"
