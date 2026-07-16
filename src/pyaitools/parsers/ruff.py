"""Ruff parsers."""

from __future__ import annotations

from pyaitools.models import CheckDef, Finding, FixHint, Location, Severity
from pyaitools.parsers.base import register
from pyaitools.parsers.common import strip_ansi
from pyaitools.parsers.patterns import DiffTextParser, JsonListParser


@register
class RuffJsonParser(JsonListParser):
    id = "ruff_json"

    def map_item(self, item: dict) -> Finding:
        filename = item.get("filename")
        location = None
        if filename:
            location = Location(
                file=filename,
                line=item.get("location", {}).get("row"),
                column=item.get("location", {}).get("column"),
                end_line=item.get("end_location", {}).get("row"),
                end_column=item.get("end_location", {}).get("column"),
            )
        code = item.get("code", "ruff")
        return Finding(
            rule_id=code,
            severity=Severity.ERROR if str(code).startswith("E") else Severity.WARNING,
            message=item.get("message", "ruff finding"),
            location=location,
            snippet=item.get("message"),
            fix=FixHint(
                description="Apply ruff auto-fix",
                command=f"ruff check --fix {filename}",
            )
            if filename
            else None,
        )


@register
class RuffFormatParser(DiffTextParser):
    id = "ruff_format_text"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = strip_ansi(stdout or stderr)
        if not text.strip():
            return []
        findings, _current_file = self._scan_lines(text.splitlines())
        if findings:
            return findings
        if "reformatted" not in text.lower():
            return []
        return [
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message="Formatting differences detected",
                snippet=text[:500],
                fix=FixHint(description="Run ruff format", command="ruff format"),
            )
        ]

    def _scan_lines(self, lines: list[str]) -> tuple[list[Finding], str | None]:
        findings: list[Finding] = []
        current_file: str | None = None
        for line in lines:
            current_file = self._file_from_line(line, current_file)
            finding = self._finding_from_line(line, current_file)
            if finding is not None:
                findings.append(finding)
                continue
            self._append_diff(findings, line, current_file)
        return findings, current_file

    def _append_diff(self, findings: list[Finding], line: str, current_file: str | None) -> None:
        if not line.startswith(("---", "+++", "@@")):
            return
        if not findings or not current_file:
            return
        findings[-1].snippet = (findings[-1].snippet or "") + line + "\n"

    def _file_from_line(self, line: str, current_file: str | None) -> str | None:
        if line.endswith(".py") or line.endswith(".py would be reformatted"):
            return strip_ansi(line.split()[0].rstrip(":"))
        if line.startswith("Would reformat:"):
            return line.split(":", 1)[1].strip()
        return current_file

    def _finding_from_line(self, line: str, current_file: str | None) -> Finding | None:
        if not line.startswith("Would reformat:"):
            return None
        return Finding(
            rule_id="format",
            severity=Severity.ERROR,
            message="File would be reformatted",
            location=Location(file=current_file) if current_file else None,
            fix=FixHint(
                description="Run ruff format",
                command=f"ruff format {current_file}" if current_file else "ruff format",
            ),
        )
