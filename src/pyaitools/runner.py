"""Execute checks with silent-on-success semantics."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from pyaitools.config_resolver import ConfigResolver
from pyaitools.gates import default_report_path
from pyaitools.gate_config import gate_env_from_config, load_gate_config
from pyaitools.registry import PACKAGE_ROOT
from pyaitools.models import (
    CheckDef,
    CheckResult,
    EnvMode,
    ProjectConfig,
    SuiteCheckRef,
    SuiteDef,
    SuiteResult,
    utc_now,
)
from pyaitools.parsers import parse_output
from pyaitools.registry import Registry
from pyaitools.reporter import Reporter
from pyaitools.resolver import BinaryResolver


class Runner:
    def __init__(self, registry: Registry, project_root: Path | None = None, verbose: bool = False) -> None:
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
        results: list[CheckResult] = []
        passed = True

        for check_ref in check_refs:
            target = self._resolve_target(check_ref, suite, project_config)
            result = self.run_check(
                check_ref.id,
                target=target,
                suite_id=suite_id,
                env_mode=env_mode,
                project_config=project_config,
            )
            results.append(result)
            if not result.passed:
                passed = False
                if fail_fast:
                    break

        return SuiteResult(suite_id=suite_id, passed=passed, results=results)

    def run_check(
        self,
        check_id: str,
        *,
        target: str,
        suite_id: str | None = None,
        env_mode: EnvMode = EnvMode.AUTO,
        project_config: ProjectConfig | None = None,
    ) -> CheckResult:
        check = self.registry.get_check(check_id)
        tool = self.registry.get_tool(check.tool)
        started_at = utc_now()
        start = time.perf_counter()

        is_script_gate = check.tool == "script" or check.script is not None
        report_rel = check.output_file or (
            default_report_path(check_id) if is_script_gate else None
        )

        try:
            if is_script_gate:
                argv, env = self._build_script_argv(
                    check, check_id, target, report_rel, project_config
                )
            else:
                binary = self.resolver.resolve(tool, env_mode)
                config_argv = self.config_resolver.extra_argv(tool.id, project_config)
                cov_target = self._resolve_cov_target(check, project_config)
                argv = [
                    str(binary),
                    *config_argv,
                    *[part.format(target=target, cov=cov_target) for part in check.argv],
                ]
                env = self.resolver.prepend_managed_path()
        except FileNotFoundError as exc:
            return CheckResult(check_id=check_id, passed=False, error=str(exc))
        except OSError as exc:
            return CheckResult(check_id=check_id, passed=False, error=str(exc))

        if report_rel and is_script_gate:
            report_path = self.project_root / report_rel
            report_path.parent.mkdir(parents=True, exist_ok=True)
            if report_path.exists():
                report_path.unlink()

        if self.verbose:
            print(f"RUN {check_id}: {' '.join(argv)}")

        completed = subprocess.run(
            argv,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            env=env,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        stdout = completed.stdout
        output_rel = report_rel if is_script_gate else check.output_file
        if output_rel:
            output_path = self.project_root / output_rel
            if output_path.exists():
                stdout = output_path.read_text(encoding="utf-8")
        try:
            findings = parse_output(check, stdout, completed.stderr)
        except (json.JSONDecodeError, ValueError) as exc:
            from pyaitools.models import Finding, Severity

            findings = [
                Finding(
                    rule_id="parser_error",
                    severity=Severity.ERROR,
                    message=f"Failed to parse tool output: {exc}",
                    snippet=(stdout or completed.stderr)[:500] or None,
                )
            ]

        exit_ok = completed.returncode in check.success.exit_codes
        passed = exit_ok and len(findings) == 0

        if passed:
            return CheckResult(check_id=check_id, passed=True)

        if not findings and not exit_ok:
            from pyaitools.models import Finding, Severity

            findings = [
                Finding(
                    rule_id="exit_code",
                    severity=Severity.ERROR,
                    message=f"Check failed with exit code {completed.returncode}",
                    snippet=(completed.stderr or stdout)[:500] or None,
                )
            ]

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

    def _resolve_target(
        self,
        check_ref: SuiteCheckRef,
        suite: SuiteDef,
        project_config: ProjectConfig | None,
    ) -> str:
        if check_ref.target:
            return check_ref.target
        check = self.registry.get_check(check_ref.id)
        target_key = check.target_key
        if project_config and project_config.targets:
            if target_key in project_config.targets:
                return project_config.targets[target_key]
        if suite.targets and target_key in suite.targets:
            return suite.targets[target_key]
        return "."

    def _resolve_cov_target(
        self,
        check,
        project_config: ProjectConfig | None,
    ) -> str:
        if check.policy and check.policy.coverage_source:
            return check.policy.coverage_source
        if project_config and project_config.targets:
            if "coverage" in project_config.targets:
                return project_config.targets["coverage"]
        return "src/"

    def _build_script_argv(
        self,
        check: CheckDef,
        check_id: str,
        target: str,
        report_rel: str | None,
        project_config: ProjectConfig | None,
    ) -> tuple[list[str], dict[str, str]]:
        if not check.script:
            raise OSError(f"Script gate '{check_id}' has no script path")

        script_path = self._resolve_script_path(check)

        if not script_path.exists():
            raise FileNotFoundError(f"Script gate not found: {script_path}")

        bash = shutil.which("bash") or "/bin/bash"
        cov_target = target
        argv = [
            bash,
            str(script_path),
            *[part.format(target=target, cov=cov_target) for part in check.argv],
        ]

        env = self.resolver.prepend_managed_path()
        env["PYAITOOLS_ROOT"] = str(self.project_root)
        env["PYAITOOLS_TARGET"] = target
        env["PYAITOOLS_CHECK_ID"] = check_id
        env["PYAITOOLS_PYTHON"] = sys.executable
        if report_rel:
            env["PYAITOOLS_REPORT"] = str(self.project_root / report_rel)

        config_path, gate_config = load_gate_config(check_id, self.project_root, project_config)
        resolved_config = self.project_root / ".pyaitools" / "cache" / f"{check_id}.config.yaml"
        resolved_config.parent.mkdir(parents=True, exist_ok=True)
        resolved_config.write_text(yaml.safe_dump(gate_config, sort_keys=False), encoding="utf-8")
        env["PYAITOOLS_GATE_CONFIG"] = str(resolved_config)
        env.update(gate_env_from_config(gate_config, self.project_root))
        return argv, env

    def _resolve_script_path(self, check: CheckDef) -> Path:
        if not check.script:
            raise OSError("missing script path")
        if check.script.startswith("bundled:"):
            return (PACKAGE_ROOT / "defaults" / check.script.removeprefix("bundled:")).resolve()
        script_path = Path(check.script)
        if not script_path.is_absolute():
            script_path = (self.project_root / script_path).resolve()
        return script_path
