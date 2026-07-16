"""Execute checks with silent-on-success semantics."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from pyossmtool.config_resolver import ConfigResolver
from pyossmtool.gates import default_report_path
from pyossmtool.ignore import (
    EffectiveIgnores,
    bundled_tool_ignore_patterns,
    filter_findings,
    ignore_env,
    materialize_for_tool,
    resolve_effective_ignores,
)
from pyossmtool.models import (
    CheckDef,
    CheckResult,
    EnvMode,
    Finding,
    ProjectConfig,
    Severity,
    SuiteCheckRef,
    SuiteDef,
    SuiteResult,
    ToolDef,
    utc_now,
)
from pyossmtool.parsers import parse_output
from pyossmtool.registry import Registry
from pyossmtool.reporter import Reporter
from pyossmtool.resolver import BinaryResolver
from pyossmtool.runner_script import build_script_argv
from pyossmtool.target_expand import (
    argv_targets_for_check,
    build_tool_argv,
    coverage_target,
    resolve_suite_target,
)


@dataclass
class _CheckLaunch:
    argv: list[str]
    env: dict[str, str]
    report_rel: str | None
    is_script_gate: bool


class Runner:
    def __init__(
        self,
        registry: Registry,
        project_root: Path | None = None,
        verbose: bool = False,
    ) -> None:
        self.registry = registry
        self.project_root = (project_root or Path.cwd()).resolve()
        self.verbose = verbose
        self.resolver = BinaryResolver(self.project_root)
        self.config_resolver = ConfigResolver(self.project_root)
        self.reporter = Reporter(self.project_root)

    def run_suite(
        self,
        suite_id: str,
        project_config: ProjectConfig | None = None,
        fail_fast: bool = False,
    ) -> SuiteResult:
        suite = self.registry.get_suite(suite_id)
        env_mode = project_config.env if project_config else suite.env
        check_refs = project_config.checks if project_config and project_config.checks else suite.checks
        results = self._run_suite_checks(suite_id, suite, check_refs, env_mode, project_config, fail_fast)
        return SuiteResult(
            suite_id=suite_id,
            passed=all(result.passed for result in results),
            results=results,
        )

    def _run_suite_checks(
        self,
        suite_id: str,
        suite: SuiteDef,
        check_refs: list[SuiteCheckRef],
        env_mode: EnvMode,
        project_config: ProjectConfig | None,
        fail_fast: bool,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for check_ref in check_refs:
            target = self._resolve_target(check_ref, suite, project_config)
            argv_targets = self._argv_targets(check_ref.id, target)
            if argv_targets is None:
                results.append(CheckResult(check_id=check_ref.id, passed=True))
                continue
            result = self.run_check(
                check_ref.id,
                target=target,
                argv_targets=argv_targets,
                suite_id=suite_id,
                env_mode=env_mode,
                project_config=project_config,
                suite=suite,
                check_ref=check_ref,
            )
            results.append(result)
            if not result.passed and fail_fast:
                break
        return results

    def run_check(
        self,
        check_id: str,
        *,
        target: str,
        suite_id: str | None = None,
        env_mode: EnvMode = EnvMode.AUTO,
        project_config: ProjectConfig | None = None,
        suite: SuiteDef | None = None,
        check_ref: SuiteCheckRef | None = None,
        argv_targets: list[str] | None = None,
    ) -> CheckResult:
        check = self.registry.get_check(check_id)
        tool = self.registry.get_tool(check.tool)
        started_at = utc_now()
        start = time.perf_counter()
        suite, check_ref = self._resolve_suite_context(check_id, suite_id, suite, check_ref, project_config)
        if argv_targets is None:
            argv_targets = self._argv_targets(check_id, target)
            if argv_targets is None:
                return CheckResult(check_id=check_id, passed=True)
        effective_ignores = resolve_effective_ignores(
            self.project_root,
            suite=suite,
            project_config=project_config,
            check_ref=check_ref,
            check=check,
            bundled_patterns=bundled_tool_ignore_patterns(tool.id),
        )
        launch = self._safe_prepare_launch(
            check,
            check_id,
            target,
            argv_targets,
            tool,
            env_mode,
            project_config,
            suite=suite,
            check_ref=check_ref,
            effective_ignores=effective_ignores,
        )
        if isinstance(launch, CheckResult):
            return launch
        return self._execute_launch(
            check_id=check_id,
            check=check,
            tool=tool,
            suite_id=suite_id,
            target=target,
            started_at=started_at,
            start=start,
            launch=launch,
            effective_ignores=effective_ignores,
        )

    def _resolve_suite_context(
        self,
        check_id: str,
        suite_id: str | None,
        suite: SuiteDef | None,
        check_ref: SuiteCheckRef | None,
        project_config: ProjectConfig | None,
    ) -> tuple[SuiteDef | None, SuiteCheckRef | None]:
        if suite is None and suite_id:
            suite = self.registry.get_suite(suite_id)
        if check_ref is None:
            check_ref = self._find_check_ref(check_id, suite, project_config)
        return suite, check_ref

    def _safe_prepare_launch(
        self,
        check: CheckDef,
        check_id: str,
        target: str,
        argv_targets: list[str],
        tool: ToolDef,
        env_mode: EnvMode,
        project_config: ProjectConfig | None,
        *,
        suite: SuiteDef | None,
        check_ref: SuiteCheckRef | None,
        effective_ignores: EffectiveIgnores,
    ) -> _CheckLaunch | CheckResult:
        try:
            return self._prepare_check_launch(
                check,
                check_id,
                target,
                argv_targets,
                tool,
                env_mode,
                project_config,
                suite=suite,
                check_ref=check_ref,
                effective_ignores=effective_ignores,
            )
        except (FileNotFoundError, OSError) as exc:
            return CheckResult(check_id=check_id, passed=False, error=str(exc))

    def _execute_launch(
        self,
        *,
        check_id: str,
        check: CheckDef,
        tool: ToolDef,
        suite_id: str | None,
        target: str,
        started_at,
        start: float,
        launch: _CheckLaunch,
        effective_ignores: EffectiveIgnores,
    ) -> CheckResult:
        self._prepare_script_report(launch)
        if self.verbose:
            print(f"RUN {check_id}: {' '.join(launch.argv)}")
        completed = subprocess.run(
            launch.argv,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            env=launch.env,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        stdout = self._read_check_stdout(completed.stdout, check, launch)
        findings = self._parse_check_findings(check, stdout, completed.stderr, effective_ignores)
        return self._finalize_check_result(
            check_id=check_id,
            check=check,
            tool=tool,
            suite_id=suite_id,
            target=target,
            started_at=started_at,
            duration_ms=duration_ms,
            completed=completed,
            findings=findings,
            stdout=stdout,
        )

    def _prepare_check_launch(
        self,
        check: CheckDef,
        check_id: str,
        target: str,
        argv_targets: list[str],
        tool: ToolDef,
        env_mode: EnvMode,
        project_config: ProjectConfig | None,
        *,
        suite: SuiteDef | None,
        check_ref: SuiteCheckRef | None,
        effective_ignores: EffectiveIgnores,
    ) -> _CheckLaunch:
        is_script_gate = check.tool == "script" or check.script is not None
        report_rel = check.output_file or (default_report_path(check_id) if is_script_gate else None)
        if is_script_gate:
            argv, env = build_script_argv(
                self,
                check,
                check_id,
                target,
                report_rel,
                project_config,
                suite=suite,
                check_ref=check_ref,
                effective_ignores=effective_ignores,
            )
            return _CheckLaunch(argv=argv, env=env, report_rel=report_rel, is_script_gate=True)

        argv, env = self._build_native_argv(
            check,
            check_id,
            argv_targets,
            tool,
            env_mode,
            project_config,
            effective_ignores=effective_ignores,
        )
        return _CheckLaunch(argv=argv, env=env, report_rel=report_rel, is_script_gate=False)

    def _build_native_argv(
        self,
        check: CheckDef,
        check_id: str,
        argv_targets: list[str],
        tool: ToolDef,
        env_mode: EnvMode,
        project_config: ProjectConfig | None,
        *,
        effective_ignores: EffectiveIgnores,
    ) -> tuple[list[str], dict[str, str]]:
        binary = self.resolver.resolve(tool, env_mode)
        base_config_path = self.config_resolver.resolve_config_path(tool, project_config)
        ignore_material = materialize_for_tool(
            tool,
            effective_ignores,
            project_root=self.project_root,
            check_id=check_id,
            base_config_path=base_config_path,
        )
        config_argv, config_value = self._native_config_argv(
            tool,
            project_config,
            ignore_material,
            base_config_path,
        )
        ignore_argv = self._native_ignore_argv(ignore_material)
        cov_target = coverage_target(check)
        argv = build_tool_argv(
            binary=str(binary),
            tool_id=tool.id,
            config_argv=config_argv,
            ignore_argv=ignore_argv,
            check_argv=check.argv,
            argv_targets=argv_targets,
            format_values={"cov": cov_target, "config": config_value},
            post_subcommand=ignore_material.post_subcommand,
        )
        env = self.resolver.prepend_managed_path()
        env.update(ignore_env(effective_ignores, self.project_root))
        return argv, env

    def _native_config_argv(
        self,
        tool: ToolDef,
        project_config: ProjectConfig | None,
        ignore_material,
        base_config_path: Path | None,
    ) -> tuple[list[str], str]:
        if ignore_material.config_path:
            return ignore_material.argv, str(ignore_material.config_path)
        config_argv = self.config_resolver.extra_argv(tool, project_config)
        config_value = str(base_config_path) if base_config_path else ""
        return config_argv, config_value

    def _native_ignore_argv(self, ignore_material) -> list[str]:
        if ignore_material.config_path:
            return []
        return ignore_material.argv

    def _prepare_script_report(self, launch: _CheckLaunch) -> None:
        if not launch.report_rel or not launch.is_script_gate:
            return
        report_path = self.project_root / launch.report_rel
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if report_path.exists():
            report_path.unlink()

    def _read_check_stdout(self, stdout: str, check: CheckDef, launch: _CheckLaunch) -> str:
        output_rel = launch.report_rel if launch.is_script_gate else check.output_file
        if not output_rel:
            return stdout
        output_path = self.project_root / output_rel
        if output_path.exists():
            return output_path.read_text(encoding="utf-8")
        return stdout

    def _parse_check_findings(
        self,
        check: CheckDef,
        stdout: str,
        stderr: str,
        effective_ignores: EffectiveIgnores,
    ) -> list[Finding]:
        try:
            findings = parse_output(check, stdout, stderr)
        except (json.JSONDecodeError, ValueError) as exc:
            findings = [
                Finding(
                    rule_id="parser_error",
                    severity=Severity.ERROR,
                    message=f"Failed to parse tool output: {exc}",
                    snippet=(stdout or stderr)[:500] or None,
                )
            ]
        return filter_findings(findings, effective_ignores)

    def _finalize_check_result(
        self,
        *,
        check_id: str,
        check: CheckDef,
        tool: ToolDef,
        suite_id: str | None,
        target: str,
        started_at,
        duration_ms: int,
        completed: subprocess.CompletedProcess[str],
        findings: list[Finding],
        stdout: str,
    ) -> CheckResult:
        exit_ok = completed.returncode in check.success.exit_codes
        if exit_ok and not findings:
            return CheckResult(check_id=check_id, passed=True)
        if not findings and not exit_ok:
            findings = [_exit_code_finding(completed.returncode, completed.stderr, stdout)]
        report_path = self.reporter.write_failure(
            check=check,
            tool=tool,
            suite_id=suite_id,
            target=target,
            started_at=started_at,
            duration_ms=duration_ms,
            findings=findings,
            stdout=stdout,
            stderr=completed.stderr,
        )
        return CheckResult(check_id=check_id, passed=False, report_path=str(report_path))

    def _find_check_ref(
        self,
        check_id: str,
        suite: SuiteDef | None,
        project_config: ProjectConfig | None,
    ) -> SuiteCheckRef | None:
        project_refs = project_config.checks if project_config and project_config.checks else None
        found = self._match_check_ref(project_refs, check_id)
        if found is not None:
            return found
        suite_refs = suite.checks if suite else None
        return self._match_check_ref(suite_refs, check_id)

    def _match_check_ref(self, refs: list[SuiteCheckRef] | None, check_id: str) -> SuiteCheckRef | None:
        if not refs:
            return None
        for ref in refs:
            if ref.id == check_id:
                return ref
        return None

    def _resolve_target(
        self,
        check_ref: SuiteCheckRef,
        suite: SuiteDef,
        project_config: ProjectConfig | None,
    ) -> str:
        return resolve_suite_target(check_ref, suite, project_config)

    def _argv_targets(self, check_id: str, target: str) -> list[str] | None:
        check = self.registry.get_check(check_id)
        return argv_targets_for_check(project_root=self.project_root, check=check, target=target)


def _exit_code_finding(returncode: int, stderr: str, stdout: str) -> Finding:
    return Finding(
        rule_id="exit_code",
        severity=Severity.ERROR,
        message=f"Check failed with exit code {returncode}",
        snippet=(stderr or stdout)[:500] or None,
    )
