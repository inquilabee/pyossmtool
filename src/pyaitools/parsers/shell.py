"""Shell tool parsers (shellcheck, shfmt)."""

from __future__ import annotations

from pyaitools.models import CheckDef, Finding, FixHint, Location, Severity
from pyaitools.parsers.base import register
from pyaitools.parsers.common import strip_ansi
from pyaitools.parsers.patterns import DiffTextParser, JsonListParser


@register
class ShellcheckParser(JsonListParser):
    id = "shellcheck_json"

    def map_item(self, item: dict) -> Finding:
        level = item.get("level", "warning")
        severity = Severity.ERROR if level in {"error", "warning"} else Severity.INFO
        return Finding(
            rule_id=f"SC{item.get('code', 0)}",
            severity=severity,
            message=item.get("message", "shellcheck finding"),
            location=Location(
                file=item.get("file", ""),
                line=item.get("line"),
                column=item.get("column"),
                end_line=item.get("endLine"),
                end_column=item.get("endColumn"),
            ),
        )


@register
class ShfmtDiffParser(DiffTextParser):
    id = "shfmt_diff"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = strip_ansi(stdout or stderr)
        if not text.strip():
            return []
        findings = self._collect_findings(text.splitlines())
        if findings:
            return findings
        return [
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message="Shell formatting differences detected",
                snippet=text[:500],
            )
        ]

    def _collect_findings(self, lines: list[str]) -> list[Finding]:
        findings: list[Finding] = []
        current_file: str | None = None
        for line in lines:
            current_file = self._file_from_diff_line(line, current_file)
            finding = self._diff_finding(line, current_file)
            if finding is not None:
                findings.append(finding)
        return findings

    def _file_from_diff_line(self, line: str, current_file: str | None) -> str | None:
        if not line.startswith(("--- ", "+++ ")):
            return current_file
        marker = line[4:].split("\t")[0].strip()
        if marker and marker != "/dev/null":
            return marker
        return current_file

    def _diff_finding(self, line: str, current_file: str | None) -> Finding | None:
        if line.startswith("@@") or not line.startswith(("-", "+")):
            return None
        return Finding(
            rule_id="format",
            severity=Severity.ERROR,
            message="Shell formatting difference",
            location=Location(file=current_file) if current_file else None,
            snippet=line[:200],
            fix=FixHint(
                description="Run shfmt -w",
                command=f"shfmt -w {current_file}" if current_file else "shfmt -w",
            ),
        )
