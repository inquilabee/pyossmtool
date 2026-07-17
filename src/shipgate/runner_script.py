"""Script gate argv/env construction for Runner."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from shipgate.constants import PROJECT_CACHE_DIR
from shipgate.gate_config import gate_env_from_config, load_gate_config
from shipgate.ignore import (
    EffectiveIgnores,
    bundled_tool_ignore_patterns,
    ignore_env,
    resolve_effective_ignores,
)
from shipgate.models import CheckDef, SuiteCheckRef, SuiteDef
from shipgate.registry import BUNDLE_ROOT

if TYPE_CHECKING:
    from shipgate.runner import Runner


def build_script_argv(
    runner: Runner,
    check: CheckDef,
    check_id: str,
    target: str,
    report_rel: str | None,
    project_config,
    *,
    suite: SuiteDef | None = None,
    check_ref: SuiteCheckRef | None = None,
    effective_ignores: EffectiveIgnores | None = None,
    cli_config: Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    script_path = require_script_path(runner, check, check_id)
    argv = script_gate_argv(runner, check, script_path, target, project_config)
    env = script_gate_env(
        runner,
        check,
        check_id,
        target,
        report_rel,
        project_config,
        suite=suite,
        check_ref=check_ref,
        effective_ignores=effective_ignores,
        cli_config=cli_config,
    )
    return argv, env


def require_script_path(runner: Runner, check: CheckDef, check_id: str) -> Path:
    if not check.script:
        raise OSError(f"Script gate '{check_id}' has no script path")
    script_path = resolve_script_path(runner, check)
    if not script_path.exists():
        raise FileNotFoundError(f"Script gate not found: {script_path}")
    return script_path


def script_gate_argv(
    runner: Runner,
    check: CheckDef,
    script_path: Path,
    target: str,
    project_config,
) -> list[str]:
    tool = runner.registry.get_tool(check.tool)
    config_path = runner.config_resolver.resolve_config_path(tool, project_config)
    config_value = str(config_path) if config_path else ""
    formatted = [part.format(target=target, cov=target, config=config_value) for part in check.argv]
    if script_path.suffix == ".py":
        return [sys.executable, str(script_path), *formatted]
    bash = shutil.which("bash") or "/bin/bash"
    return [bash, str(script_path), *formatted]


def script_gate_env(
    runner: Runner,
    check: CheckDef,
    check_id: str,
    target: str,
    report_rel: str | None,
    project_config,
    *,
    suite: SuiteDef | None,
    check_ref: SuiteCheckRef | None,
    effective_ignores: EffectiveIgnores | None,
    cli_config: Path | None = None,
) -> dict[str, str]:
    env = runner.resolver.prepend_managed_path()
    env.update(
        {
            "SHIPGATE_ROOT": str(runner.project_root),
            "SHIPGATE_TARGET": target,
            "SHIPGATE_CHECK_ID": check_id,
            "SHIPGATE_PYTHON": sys.executable,
        }
    )
    if report_rel:
        env["SHIPGATE_REPORT"] = str(runner.project_root / report_rel)
    _config_path, gate_config = load_gate_config(check, runner.project_root, project_config, cli_config=cli_config)
    resolved_config = runner.project_root / PROJECT_CACHE_DIR / f"{check_id}.config.yaml"
    resolved_config.parent.mkdir(parents=True, exist_ok=True)
    resolved_config.write_text(yaml.safe_dump(gate_config, sort_keys=False), encoding="utf-8")
    env["SHIPGATE_GATE_CONFIG"] = str(resolved_config)
    env.update(gate_env_from_config(gate_config, runner.project_root))
    if effective_ignores is None:
        effective_ignores = resolve_effective_ignores(
            runner.project_root,
            suite=suite,
            project_config=project_config,
            check_ref=check_ref,
            check=check,
            bundled_patterns=bundled_tool_ignore_patterns(check.tool),
        )
    env.update(ignore_env(effective_ignores, runner.project_root))
    return env


def resolve_script_path(runner: Runner, check: CheckDef) -> Path:
    if not check.script:
        raise OSError("missing script path")
    if check.script.startswith("bundled:"):
        return (BUNDLE_ROOT / "defaults" / check.script.removeprefix("bundled:")).resolve()
    script_path = Path(check.script)
    if script_path.is_absolute():
        return script_path
    return _resolve_relative_script(runner, script_path)


def _resolve_relative_script(runner: Runner, script_path: Path) -> Path:
    under_project = (runner.project_root / script_path).resolve()
    if under_project.exists() or runner.tools_root == runner.project_root:
        return under_project
    under_tools = (runner.tools_root / script_path).resolve()
    if under_tools.exists():
        return under_tools
    return under_project
