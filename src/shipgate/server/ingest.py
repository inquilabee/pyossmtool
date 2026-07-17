"""Ingest FailureReport / SuiteResult data into report-server storage."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from shipgate.models import CheckResult, FailureReport, Finding, SuiteResult
from shipgate.paths import normalize_finding_path
from shipgate.server.models import FindingCategory, FindingRecord, RunSummaryRecord
from shipgate.server.storage.base import Storage

_TOOL_RULE_IDS = frozenset({"exit_code", "pydeps-error", "parser_error", "setup"})
_TOOL_MESSAGE_MARKERS = (
    "modulenotfounderror",
    "no module named",
    "not available with this tier",
    "please upgrade at",
    "could not resolve",
    "failed to install",
    "failed to parse tool output",
)
_PYTEST_SETUP_MARKERS = (
    "interrupted",
    "error collecting",
    "errors during collection",
    "modulenotfounderror",
    "no module named",
)


def ingest_suite_result(
    storage: Storage,
    run_id: str,
    suite_result: SuiteResult,
    project_root: Path,
) -> RunSummaryRecord:
    findings: list[FindingRecord] = []
    by_severity: dict[str, int] = {}
    by_check_id: dict[str, int] = {}
    for check in suite_result.results:
        _ingest_check(check, run_id, project_root, findings, by_severity, by_check_id)
    summary = _summarize(findings, by_severity, by_check_id)
    storage.replace_findings(run_id, findings)
    return summary


def _ingest_check(
    check: CheckResult,
    run_id: str,
    project_root: Path,
    findings: list[FindingRecord],
    by_severity: dict[str, int],
    by_check_id: dict[str, int],
) -> None:
    if check.passed:
        by_check_id[check.check_id] = 0
        return
    setup = _check_setup_error(check, run_id)
    if setup is not None:
        findings.append(setup)
        return
    _ingest_report(check, run_id, project_root, findings, by_severity, by_check_id)


def _check_setup_error(check: CheckResult, run_id: str) -> FindingRecord | None:
    if check.error:
        return _setup_error_record(run_id=run_id, check_id=check.check_id, message=check.error)
    if check.report_path is None:
        return _setup_error_record(
            run_id=run_id,
            check_id=check.check_id,
            message="Check failed without a failure report",
        )
    return None


def _ingest_report(
    check: CheckResult,
    run_id: str,
    project_root: Path,
    findings: list[FindingRecord],
    by_severity: dict[str, int],
    by_check_id: dict[str, int],
) -> None:
    raw_path = check.report_path
    if raw_path is None:
        return
    report_path = Path(raw_path)
    if not report_path.is_absolute():
        report_path = project_root / report_path
    report = FailureReport.model_validate(json.loads(report_path.read_text(encoding="utf-8")))
    check_code = 0
    for finding in report.findings:
        record = _finding_to_record(finding=finding, run_id=run_id, report=report, project_root=project_root)
        findings.append(record)
        if record.category == FindingCategory.CODE:
            check_code += 1
            by_severity[record.severity] = by_severity.get(record.severity, 0) + 1
    by_check_id[check.check_id] = check_code


def _summarize(
    findings: list[FindingRecord],
    by_severity: dict[str, int],
    by_check_id: dict[str, int],
) -> RunSummaryRecord:
    code_count = sum(1 for f in findings if f.category == FindingCategory.CODE)
    tool_count = sum(1 for f in findings if f.category == FindingCategory.TOOL)
    return RunSummaryRecord(
        finding_count=code_count,
        tool_failure_count=tool_count,
        by_severity=by_severity,
        by_check_id=by_check_id,
    )


def _is_tool_failure(finding: Finding) -> bool:
    if finding.rule_id in _TOOL_RULE_IDS:
        return True
    if finding.location is not None:
        return False
    return _message_indicates_tool_failure(finding.rule_id, finding.message.lower())


def _message_indicates_tool_failure(rule_id: str, message_l: str) -> bool:
    if any(marker in message_l for marker in _TOOL_MESSAGE_MARKERS):
        return True
    return _rule_specific_tool_failure(rule_id, message_l)


def _rule_specific_tool_failure(rule_id: str, message_l: str) -> bool:
    if rule_id == "sourcery":
        return "tier" in message_l or "upgrade" in message_l
    if rule_id == "pytest":
        return _is_pytest_setup_failure(message_l)
    return False


def _is_pytest_setup_failure(message_l: str) -> bool:
    """Collection/import failures only — not coverage threshold or normal test failures."""
    if "fail-under" in message_l or "coverage failure" in message_l:
        return False
    return any(marker in message_l for marker in _PYTEST_SETUP_MARKERS)


def _setup_error_record(*, run_id: str, check_id: str, message: str) -> FindingRecord:
    tool_id = check_id.split(".", 1)[0]
    return FindingRecord(
        id=uuid.uuid4().hex,
        run_id=run_id,
        check_id=check_id,
        tool_id=tool_id,
        rule_id="setup",
        severity="error",
        message=message,
        category=FindingCategory.TOOL,
    )


def _finding_to_record(
    *,
    finding: Finding,
    run_id: str,
    report: FailureReport,
    project_root: Path | None = None,
) -> FindingRecord:
    location = finding.location
    category = FindingCategory.TOOL if _is_tool_failure(finding) else FindingCategory.CODE
    raw_file = location.file if location else None
    return FindingRecord(
        id=uuid.uuid4().hex,
        run_id=run_id,
        check_id=report.check_id,
        tool_id=report.tool_id,
        rule_id=finding.rule_id,
        severity=finding.severity.value,
        message=finding.message,
        file=normalize_finding_path(raw_file, project_root=project_root),
        line=location.line if location else None,
        column=location.column if location else None,
        docs_url=report.remediation.docs_url,
        suggested_commands=list(report.remediation.suggested_commands),
        category=category,
    )
