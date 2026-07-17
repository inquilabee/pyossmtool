"""Tests for failure error formatters."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shipgate.error_formatters import (
    CompactErrorFormatter,
    GithubErrorFormatter,
    JsonErrorFormatter,
    LogErrorFormatter,
    TextErrorFormatter,
    resolve_error_formatter,
)
from shipgate.models import (
    ErrorFormatterKind,
    ErrorFormatterSpec,
    FailureReport,
    FailureSummary,
    Finding,
    Location,
    ProjectConfig,
    Severity,
)


def _report() -> FailureReport:
    return FailureReport(
        check_id="ruff.lint",
        tool_id="ruff",
        suite_id="python-quality",
        target=".",
        started_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        duration_ms=10,
        summary=FailureSummary(finding_count=1, by_severity={"error": 1}),
        findings=[
            Finding(
                rule_id="E501",
                severity=Severity.ERROR,
                message="Line too long",
                location=Location(file="src/app.py", line=42, column=1),
            )
        ],
    )


def test_default_error_format_is_json() -> None:
    config = ProjectConfig(suite="all")
    assert config.error_format == "json"
    formatter = resolve_error_formatter(config)
    assert formatter.id == "json"
    text = formatter.format(_report(), report_path="reports/failures/x/report.json")
    assert '"check_id": "ruff.lint"' in text
    assert '"report_path"' in text


def test_log_formatter_emits_finding_lines() -> None:
    text = LogErrorFormatter().format(_report(), report_path="r.json")
    assert "FAIL ruff.lint findings=1 -> r.json" in text
    assert "[error] ruff.lint/E501 src/app.py:42: Line too long" in text


def test_text_formatter_lists_findings() -> None:
    text = TextErrorFormatter().format(_report())
    assert "FAIL ruff.lint" in text
    assert "E501: Line too long" in text


def test_github_formatter_emits_annotations() -> None:
    text = GithubErrorFormatter().format(_report())
    assert text == ("::error file=src/app.py,title=ruff.lint/E501,line=42,col=1::Line too long")


def test_github_formatter_maps_warning_and_info() -> None:
    report = _report()
    report.findings[0].severity = Severity.WARNING
    assert GithubErrorFormatter().format(report).startswith("::warning ")
    report.findings[0].severity = Severity.INFO
    assert GithubErrorFormatter().format(report).startswith("::notice ")


def test_compact_formatter_emits_file_line() -> None:
    text = CompactErrorFormatter().format(_report())
    assert text == "src/app.py:42: error: E501 Line too long"


def test_resolve_builtin_github_and_compact() -> None:
    assert resolve_error_formatter(ProjectConfig(suite="all", error_format="github")).id == "github"
    assert resolve_error_formatter(ProjectConfig(suite="all", error_format="compact")).id == "compact"


def test_custom_finding_line_formatter_from_config() -> None:
    config = ProjectConfig(
        suite="all",
        error_format="short",
        error_formatters={
            "short": ErrorFormatterSpec(
                kind=ErrorFormatterKind.FINDING_LINE,
                template="{severity}\t{rule_id}\t{file}:{line}\t{message}",
            )
        },
    )
    formatter = resolve_error_formatter(config)
    assert formatter.format(_report()) == "error\tE501\tsrc/app.py:42\tLine too long"


def test_unknown_error_format_raises() -> None:
    config = ProjectConfig(suite="all", error_format="nope")
    with pytest.raises(KeyError, match="Unknown error_format"):
        resolve_error_formatter(config)


def test_json_formatter_without_project_config() -> None:
    formatter = resolve_error_formatter(None)
    assert isinstance(formatter, JsonErrorFormatter)
