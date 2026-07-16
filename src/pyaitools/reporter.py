"""Write normalized failure reports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pyaitools.models import (
    CheckDef,
    FailureArtifacts,
    FailureReport,
    Finding,
    Remediation,
    ToolDef,
    summarize_findings,
)


_DEFAULT_COMMANDS: dict[str, str] = {
    "ruff.lint": "{binary} check --fix {target}",
    "ruff.format": "{binary} format {target}",
    "shfmt.format": "{binary} -w {target}",
    "mdformat.format": "{binary} {target}",
    "yamlfmt.format": "{binary} {target}",
    "ty.check": "{binary} check {target}",
}


class Reporter:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.failures_dir = self.project_root / "reports" / "failures"

    def write_failure(
        self,
        *,
        check: CheckDef,
        tool: ToolDef,
        suite_id: str | None,
        target: str,
        started_at: datetime,
        duration_ms: int,
        findings: list[Finding],
        stdout: str,
        stderr: str,
    ) -> Path:
        self.failures_dir.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        report_dir = self.failures_dir / f"{check.id}-{timestamp}"
        report_dir.mkdir(parents=True, exist_ok=True)

        raw_stdout_path = report_dir / "raw.stdout.txt"
        raw_stderr_path = report_dir / "raw.stderr.txt"
        raw_stdout_path.write_text(stdout, encoding="utf-8")
        raw_stderr_path.write_text(stderr, encoding="utf-8")

        cov_target = (
            check.policy.coverage_source
            if check.policy and check.policy.coverage_source
            else "src/"
        )
        remediation = Remediation(
            docs_url=tool.documentation_url,
            suggested_commands=[
                cmd.format(target=target, cov=cov_target)
                for cmd in check.remediation.get("suggested_commands", [])
            ],
        )
        if not remediation.suggested_commands:
            remediation.suggested_commands = self._default_commands(check, tool, target)

        report = FailureReport(
            check_id=check.id,
            tool_id=tool.id,
            suite_id=suite_id,
            target=target,
            started_at=started_at,
            duration_ms=duration_ms,
            summary=summarize_findings(findings),
            findings=findings,
            remediation=remediation,
            artifacts=FailureArtifacts(
                raw_stdout=str(raw_stdout_path.relative_to(self.project_root)),
                raw_stderr=str(raw_stderr_path.relative_to(self.project_root)),
            ),
        )

        report_path = report_dir / "report.json"
        report_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        return report_path

    def _default_commands(self, check: CheckDef, tool: ToolDef, target: str) -> list[str]:
        template = _DEFAULT_COMMANDS.get(check.id)
        if template:
            return [template.format(binary=tool.binary, target=target)]
        if check.tool == "script" and check.script:
            if check.script.startswith("bundled:"):
                return [f"pyaitools run --check {check.id} --target {target}"]
            return [f"./{check.script}"]
        return [f"{tool.binary} {target}"]
