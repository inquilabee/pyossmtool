"""Extra tests to raise coverage on reporter, formatters, and runner helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shipgate.error_formatters import (
    GithubErrorFormatter,
    JqErrorFormatter,
    LogErrorFormatter,
    resolve_error_formatter,
)
from shipgate.models import (
    CheckDef,
    ErrorFormatterKind,
    ErrorFormatterSpec,
    FailureReport,
    FailureSummary,
    Finding,
    InstallMethod,
    InstallSpec,
    ProjectConfig,
    Severity,
    ToolDef,
)
from shipgate.registry import Registry
from shipgate.reporter import Reporter
from shipgate.runner import Runner


def _report(*, findings: list[Finding] | None = None) -> FailureReport:
    if findings is None:
        items = [
            Finding(rule_id="E501", severity=Severity.ERROR, message="Line too long", location=None),
        ]
    else:
        items = findings
    return FailureReport(
        check_id="ruff.lint",
        tool_id="ruff",
        suite_id="all-lint",
        target=".",
        started_at=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=5,
        summary=FailureSummary(finding_count=len(items), by_severity={"error": len(items)}),
        findings=items,
    )


def test_reporter_writes_failure_artifacts(tmp_path: Path) -> None:
    check = CheckDef(
        id="ruff.lint",
        tool="ruff",
        name="ruff",
        description="lint",
        parser="ruff",
        argv=["check"],
        remediation={"suggested_commands": ["ruff check {target}"]},
    )
    tool = ToolDef(
        id="ruff",
        name="ruff",
        description="ruff",
        install=InstallSpec(method=InstallMethod.SKIP),
        binary="ruff",
    )
    path = Reporter(tmp_path).write_failure(
        check=check,
        tool=tool,
        suite_id="all-lint",
        target=".",
        started_at=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=12,
        findings=[Finding(rule_id="E501", severity=Severity.ERROR, message="oops")],
        stdout="out",
        stderr="err",
    )
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["check_id"] == "ruff.lint"
    assert (tmp_path / payload["artifacts"]["raw_stdout"]).read_text(encoding="utf-8") == "out"


def test_reporter_fallback_commands_for_script_gate(tmp_path: Path) -> None:
    reporter = Reporter(tmp_path)
    check = CheckDef(
        id="gate.demo",
        tool="script",
        name="demo",
        description="demo",
        parser="script",
        script="bundled:gates/demo.sh",
    )
    tool = ToolDef(
        id="script",
        name="script",
        description="script",
        install=InstallSpec(method=InstallMethod.SKIP),
        binary="script",
    )
    commands = reporter._fallback_commands(check, tool, ".")
    assert commands == ["shipgate check --check gate.demo --target ."]


def test_github_formatter_without_location_or_findings() -> None:
    report = _report(findings=[])
    text = GithubErrorFormatter().format(report)
    assert "failed (no findings)" in text
    report.findings = [Finding(rule_id="X", severity=Severity.ERROR, message="boom")]
    text = GithubErrorFormatter().format(report)
    assert "boom" in text


def test_log_formatter_without_report_path() -> None:
    text = LogErrorFormatter().format(_report())
    assert text.startswith("FAIL ruff.lint findings=1")


def test_jq_formatter_runs_program() -> None:
    formatter = JqErrorFormatter("jqfmt", ".check_id")
    with (
        patch("shipgate.error_formatters.shutil.which", return_value="/usr/bin/jq"),
        patch(
            "shipgate.error_formatters.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="ruff.lint\n", stderr=""),
        ),
    ):
        assert formatter.format(_report(), report_path="r.json") == "ruff.lint"


def test_jq_formatter_missing_binary_raises() -> None:
    formatter = JqErrorFormatter("jqfmt", ".check_id")
    with patch("shipgate.error_formatters.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="jq is required"):
            formatter.format(_report())


def test_resolve_jq_formatter_from_config() -> None:
    config = ProjectConfig(
        suite="all",
        error_format="jqout",
        error_formatters={"jqout": ErrorFormatterSpec(kind=ErrorFormatterKind.JQ, program=".tool_id")},
    )
    formatter = resolve_error_formatter(config)
    assert formatter.id == "jqout"


def test_jq_formatter_subprocess_failure_raises() -> None:
    formatter = JqErrorFormatter("jqfmt", "invalid jq")
    with (
        patch("shipgate.error_formatters.shutil.which", return_value="/usr/bin/jq"),
        patch(
            "shipgate.error_formatters.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="parse error"),
        ),
    ):
        with pytest.raises(RuntimeError, match="jq formatter"):
            formatter.format(_report())


def test_finding_line_formatter_without_findings() -> None:
    from shipgate.error_formatters import FindingLineErrorFormatter

    text = FindingLineErrorFormatter("line", "{check_id}").format(_report(findings=[]))
    assert text == "FAIL ruff.lint (no findings)"


def test_compact_formatter_without_findings() -> None:
    from shipgate.error_formatters import CompactErrorFormatter

    text = CompactErrorFormatter().format(_report(findings=[]))
    assert "failed (no findings)" in text


def test_format_report_file_roundtrip(tmp_path: Path) -> None:
    from shipgate.error_formatters import JsonErrorFormatter, format_report_file

    path = tmp_path / "report.json"
    path.write_text(_report().model_dump_json(), encoding="utf-8")
    text = format_report_file(path, JsonErrorFormatter())
    assert '"check_id": "ruff.lint"' in text


def test_text_formatter_includes_report_path_and_remediation() -> None:
    from shipgate.error_formatters import TextErrorFormatter
    from shipgate.models import Remediation

    report = _report()
    report.remediation = Remediation(suggested_commands=["ruff check ."])
    text = TextErrorFormatter().format(report, report_path="reports/x.json")
    assert "-> reports/x.json" in text
    assert "suggested:" in text


def test_unsupported_formatter_kind_raises() -> None:
    from shipgate.error_formatters import _formatter_from_spec
    from shipgate.models import ErrorFormatterSpec

    spec = ErrorFormatterSpec.model_construct(kind="bogus", template=None, program=None)
    with pytest.raises(ValueError, match="Unsupported error formatter kind"):
        _formatter_from_spec("bad", spec)


def test_runner_with_project_virtualenv_uses_venv_bin(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = .\n", encoding="utf-8")
    (bin_dir / "python").write_text("", encoding="utf-8")
    runner = Runner(Registry(project_root=tmp_path), project_root=tmp_path, tools_root=tmp_path)
    env = runner._with_project_virtualenv({"PATH": "/usr/bin"})
    assert env["VIRTUAL_ENV"] == str(venv.resolve())
    assert str(bin_dir) in env["PATH"]
