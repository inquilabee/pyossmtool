"""Format FailureReport objects for CLI/stderr presentation."""

from __future__ import annotations

import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from shipgate.models import (
    ErrorFormatterKind,
    ErrorFormatterSpec,
    FailureReport,
    Finding,
    Location,
    ProjectConfig,
)

BUILTIN_FORMATS = frozenset({"json", "log", "text", "github", "compact"})


class ErrorFormatter(ABC):
    id: str

    @abstractmethod
    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        raise NotImplementedError


class JsonErrorFormatter(ErrorFormatter):
    id = "json"

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        payload = report.model_dump(mode="json")
        if report_path:
            payload["report_path"] = report_path
        return json.dumps(payload, indent=2)


class LogErrorFormatter(ErrorFormatter):
    id = "log"

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        header = f"FAIL {report.check_id} findings={report.summary.finding_count}"
        if report_path:
            header += f" -> {report_path}"
        lines = [header]
        started = report.started_at.isoformat()
        for finding in report.findings:
            loc = _finding_location(finding.location) or "-"
            lines.append(
                f"{started} [{finding.severity.value}] {report.check_id}/{finding.rule_id} {loc}: {finding.message}"
            )
        return "\n".join(lines)


class TextErrorFormatter(ErrorFormatter):
    id = "text"

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        header = f"FAIL {report.check_id}"
        if report_path:
            header += f" -> {report_path}"
        lines = [header, f"findings: {report.summary.finding_count}"]
        for finding in report.findings:
            loc = _finding_location(finding.location)
            suffix = f" ({loc})" if loc else ""
            lines.append(f"- [{finding.severity.value}] {finding.rule_id}: {finding.message}{suffix}")
        lines.extend(_suggested_lines(report))
        return "\n".join(lines)


class GithubErrorFormatter(ErrorFormatter):
    """GitHub Actions workflow commands for inline annotations."""

    id = "github"

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        del report_path  # annotations are file-local; path stays on disk only
        lines = [_github_finding_line(report, finding) for finding in report.findings]
        if not lines:
            default = f"{report.check_id} failed (no findings)"
            return f"::error title={_github_escape_property(report.check_id)}::{_github_escape_data(default)}"
        return "\n".join(lines)


class CompactErrorFormatter(ErrorFormatter):
    """Editor-friendly one line per finding: file:line: severity: rule message."""

    id = "compact"

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        del report_path
        lines = [_compact_finding_line(finding) for finding in report.findings]
        if not lines:
            lines.append(f"-:?: error: {report.check_id} failed (no findings)")
        return "\n".join(lines)


def _finding_line_label(location: Location | None) -> str:
    if location and location.line is not None:
        return str(location.line)
    return "?"


def _finding_file_label(location: Location | None) -> str:
    if location and location.file:
        return location.file
    return "-"


def _finding_location(location: Location | None) -> str | None:
    """Return 'file:line' when a file is present, else None."""
    if not location or not location.file:
        return None
    return f"{location.file}:{_finding_line_label(location)}"


def _suggested_lines(report: FailureReport) -> list[str]:
    if not report.remediation.suggested_commands:
        return []
    return ["suggested:", *(f"  {cmd}" for cmd in report.remediation.suggested_commands)]


def _github_finding_line(report: FailureReport, finding: Finding) -> str:
    cmd = _github_command(finding.severity.value)
    title = f"{report.check_id}/{finding.rule_id}"
    params: list[str] = [f"title={_github_escape_property(title)}"]
    location = finding.location
    if location and location.file:
        params.insert(0, f"file={_github_escape_property(location.file)}")
        if location.line is not None:
            params.append(f"line={location.line}")
        if location.column is not None:
            params.append(f"col={location.column}")
    message = _github_escape_data(finding.message)
    return f"::{cmd} {','.join(params)}::{message}"


def _compact_finding_line(finding: Finding) -> str:
    file = _finding_file_label(finding.location)
    line = _finding_line_label(finding.location)
    return f"{file}:{line}: {finding.severity.value}: {finding.rule_id} {finding.message}"


def _github_command(severity: str) -> str:
    if severity == "warning":
        return "warning"
    if severity in {"info", "note"}:
        return "notice"
    return "error"


def _github_escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _github_escape_property(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C")


class FindingLineErrorFormatter(ErrorFormatter):
    """Template per finding; placeholders: severity, rule_id, message, file, line, check_id."""

    def __init__(self, formatter_id: str, template: str) -> None:
        self.id = formatter_id
        self.template = template

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        lines = [self.template.format(**self._values(report, finding, report_path)) for finding in report.findings]
        if not lines:
            lines.append(f"FAIL {report.check_id} (no findings)")
        return "\n".join(lines)

    @staticmethod
    def _values(report: FailureReport, finding: Finding, report_path: str | None) -> dict[str, str]:
        return {
            "severity": finding.severity.value,
            "rule_id": finding.rule_id,
            "message": finding.message,
            "check_id": report.check_id,
            "file": finding.location.file if finding.location else "-",
            "line": _finding_line_label(finding.location),
            "report_path": report_path or "",
        }


class JqErrorFormatter(ErrorFormatter):
    def __init__(self, formatter_id: str, program: str) -> None:
        self.id = formatter_id
        self.program = program

    def format(self, report: FailureReport, *, report_path: str | None = None) -> str:
        jq_bin = shutil.which("jq")
        if not jq_bin:
            raise RuntimeError("jq is required for error formatter kind 'jq' but was not found on PATH")
        payload = report.model_dump(mode="json")
        if report_path:
            payload["report_path"] = report_path
        completed = subprocess.run(
            [jq_bin, "-r", self.program],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"jq formatter '{self.id}' failed: {_jq_error_detail(completed)}")
        return completed.stdout.rstrip("\n")


def _jq_error_detail(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "jq failed").strip()


def _configured_format(project_config: ProjectConfig | None) -> tuple[str, dict[str, ErrorFormatterSpec]]:
    if project_config is None:
        return "json", {}
    return project_config.error_format or "json", project_config.error_formatters


def _builtin_formatter(format_id: str) -> ErrorFormatter:
    builtins: dict[str, ErrorFormatter] = {
        "json": JsonErrorFormatter(),
        "log": LogErrorFormatter(),
        "text": TextErrorFormatter(),
        "github": GithubErrorFormatter(),
        "compact": CompactErrorFormatter(),
    }
    return builtins[format_id]


def resolve_error_formatter(project_config: ProjectConfig | None) -> ErrorFormatter:
    format_id, custom = _configured_format(project_config)
    if format_id in custom:
        return _formatter_from_spec(format_id, custom[format_id])
    if format_id not in BUILTIN_FORMATS:
        known = ", ".join([*sorted(BUILTIN_FORMATS), *sorted(custom)])
        raise KeyError(f"Unknown error_format '{format_id}' (known: {known})")
    return _builtin_formatter(format_id)


def _formatter_from_spec(formatter_id: str, spec: ErrorFormatterSpec) -> ErrorFormatter:
    if spec.kind == ErrorFormatterKind.JQ:
        assert spec.program is not None
        return JqErrorFormatter(formatter_id, spec.program)
    if spec.kind == ErrorFormatterKind.FINDING_LINE:
        assert spec.template is not None
        return FindingLineErrorFormatter(formatter_id, spec.template)
    raise ValueError(f"Unsupported error formatter kind: {spec.kind}")


def format_report_file(
    report_path: str | Path,
    formatter: ErrorFormatter,
) -> str:
    path = Path(report_path)
    report = FailureReport.model_validate_json(path.read_text(encoding="utf-8"))
    return formatter.format(report, report_path=str(path))
