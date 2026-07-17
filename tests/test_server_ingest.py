import json
from datetime import UTC, datetime
from pathlib import Path

from shipgate.models import (
    CheckResult,
    FailureArtifacts,
    FailureReport,
    FailureSummary,
    Finding,
    Location,
    Severity,
    SuiteResult,
)
from shipgate.server.ingest import ingest_suite_result
from shipgate.server.models import FindingCategory
from shipgate.server.storage.sqlite import SqliteStorage


def _write_report(tmp_path: Path, check_id: str, tool_id: str, findings: list[Finding]) -> Path:
    report_dir = tmp_path / "reports" / "failures" / f"{check_id}-1"
    report_dir.mkdir(parents=True)
    report = FailureReport(
        check_id=check_id,
        tool_id=tool_id,
        suite_id="all",
        target=".",
        started_at=datetime.now(UTC),
        duration_ms=10,
        summary=FailureSummary(
            finding_count=len(findings),
            by_severity={f.severity.value: 1 for f in findings},
        ),
        findings=findings,
        artifacts=FailureArtifacts(),
    )
    report_path = report_dir / "report.json"
    report_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    return report_path


def test_ingest_reads_failure_report(tmp_path: Path) -> None:
    report_path = _write_report(
        tmp_path,
        "ruff.lint",
        "ruff",
        [
            Finding(
                rule_id="E501",
                severity=Severity.ERROR,
                message="too long",
                location=Location(file="a.py", line=2),
            )
        ],
    )

    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    suite_result = SuiteResult(
        suite_id="all",
        passed=False,
        results=[
            CheckResult(check_id="ruff.lint", passed=False, report_path=str(report_path)),
            CheckResult(check_id="ty.check", passed=True),
        ],
    )
    summary = ingest_suite_result(storage, run.id, suite_result, tmp_path)
    assert summary.finding_count == 1
    assert summary.tool_failure_count == 0
    assert summary.by_check_id["ruff.lint"] == 1
    assert summary.by_check_id["ty.check"] == 0
    assert storage.list_findings(run.id)[0].file == "a.py"
    assert storage.list_findings(run.id)[0].category == FindingCategory.CODE


def test_ingest_normalizes_dot_slash_paths(tmp_path: Path) -> None:
    report_path = _write_report(
        tmp_path,
        "bandit.scan",
        "bandit",
        [
            Finding(
                rule_id="B101",
                severity=Severity.WARNING,
                message="assert",
                location=Location(file="./src/foo.py", line=3),
            )
        ],
    )
    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    suite_result = SuiteResult(
        suite_id="all",
        passed=False,
        results=[CheckResult(check_id="bandit.scan", passed=False, report_path=str(report_path))],
    )
    ingest_suite_result(storage, run.id, suite_result, tmp_path)
    finding = storage.list_findings(run.id)[0]
    assert finding.file == "src/foo.py"
    assert storage.list_findings(run.id, file="./src/foo.py")[0].file == "src/foo.py"


def test_ingest_separates_tool_failures_from_code_findings(tmp_path: Path) -> None:
    code_report = _write_report(
        tmp_path,
        "ruff.lint",
        "ruff",
        [
            Finding(
                rule_id="E501",
                severity=Severity.ERROR,
                message="too long",
                location=Location(file="a.py", line=2),
            )
        ],
    )
    tool_report = _write_report(
        tmp_path,
        "mutmut.run",
        "mutmut",
        [
            Finding(
                rule_id="mutmut",
                severity=Severity.ERROR,
                message="ModuleNotFoundError: No module named 'typer'",
            )
        ],
    )
    exit_report = _write_report(
        tmp_path,
        "pydeps.check",
        "pydeps",
        [
            Finding(
                rule_id="exit_code",
                severity=Severity.ERROR,
                message="Check failed with exit code 1",
            )
        ],
    )

    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    suite_result = SuiteResult(
        suite_id="all",
        passed=False,
        results=[
            CheckResult(check_id="ruff.lint", passed=False, report_path=str(code_report)),
            CheckResult(check_id="mutmut.run", passed=False, report_path=str(tool_report)),
            CheckResult(check_id="pydeps.check", passed=False, report_path=str(exit_report)),
            CheckResult(check_id="bandit.scan", passed=False, error="Failed to install bandit"),
        ],
    )
    summary = ingest_suite_result(storage, run.id, suite_result, tmp_path)

    assert summary.finding_count == 1
    assert summary.tool_failure_count == 3
    assert summary.by_check_id["ruff.lint"] == 1
    assert "mutmut.run" not in summary.by_check_id or summary.by_check_id.get("mutmut.run", 0) == 0

    code = storage.list_findings(run.id, category=FindingCategory.CODE)
    tools = storage.list_findings(run.id, category=FindingCategory.TOOL)
    assert len(code) == 1
    assert code[0].rule_id == "E501"
    assert len(tools) == 3
    assert {f.check_id for f in tools} == {"mutmut.run", "pydeps.check", "bandit.scan"}
    setup = next(f for f in tools if f.check_id == "bandit.scan")
    assert setup.rule_id == "setup"
    assert setup.message == "Failed to install bandit"


def test_ingest_coverage_threshold_is_code_not_tool_failure(tmp_path: Path) -> None:
    report_path = _write_report(
        tmp_path,
        "pytest.coverage",
        "pytest",
        [
            Finding(
                rule_id="pytest",
                severity=Severity.ERROR,
                message="ERROR: Coverage failure: total of 52 is less than fail-under=80",
            ),
            Finding(
                rule_id="pytest",
                severity=Severity.ERROR,
                message="!!!!!!!!!!!!!!!!!!! Interrupted: 11 errors during collection !!!!!!!!!!!!!!!!!!!",
            ),
        ],
    )
    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    suite_result = SuiteResult(
        suite_id="all",
        passed=False,
        results=[
            CheckResult(check_id="pytest.coverage", passed=False, report_path=str(report_path)),
        ],
    )
    summary = ingest_suite_result(storage, run.id, suite_result, tmp_path)
    assert summary.finding_count == 1
    assert summary.tool_failure_count == 1
    code = storage.list_findings(run.id, category=FindingCategory.CODE)
    tools = storage.list_findings(run.id, category=FindingCategory.TOOL)
    assert len(code) == 1
    assert "fail-under" in code[0].message
    assert len(tools) == 1
    assert "collection" in tools[0].message.lower()
