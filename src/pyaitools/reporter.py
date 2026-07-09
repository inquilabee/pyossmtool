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
    utc_now,
)


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

        remediation = Remediation(
            docs_url=tool.documentation_url,
            suggested_commands=[
                cmd.format(target=target) for cmd in check.remediation.get("suggested_commands", [])
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
        if check.id == "ruff.lint":
            return [f"{tool.binary} check --fix {target}"]
        if check.id == "ruff.format":
            return [f"{tool.binary} format {target}"]
        if check.id == "shfmt.format":
            return [f"{tool.binary} -w {target}"]
        if check.id == "mdformat.format":
            return [f"{tool.binary} {target}"]
        if check.id == "yamlfmt.format":
            return [f"{tool.binary} {target}"]
        if check.id == "ty.check":
            return [f"{tool.binary} check {target}"]
        if check.tool == "script" and check.script:
            script = check.script.removeprefix("bundled:")
            if check.script.startswith("bundled:"):
                return [f"pyaitools run --check {check.id} --target {target}"]
            return [f"./{check.script}"]
        return [f"{tool.binary} {target}"]
