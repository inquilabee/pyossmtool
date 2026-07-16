"""Analysis-tool output parsers (radon, ty, pytest, etc.)."""

from __future__ import annotations

import json
import re

from pyaitools.models import CheckDef, Finding, Location, Severity
from pyaitools.parsers.common import RANK_ORDER


def parse_ty(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings = [
        finding for line in text.splitlines() if (finding := _ty_line_finding(line)) is not None
    ]
    if findings:
        return findings
    return _ty_summary_findings(text)


_TY_PATTERN = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<kind>\w+):\s*(?P<message>.+)$"
)


def _ty_line_finding(line: str) -> Finding | None:
    match = _TY_PATTERN.match(line.strip())
    if not match:
        return None
    return Finding(
        rule_id=match.group("kind"),
        severity=Severity.ERROR,
        message=match.group("message"),
        location=Location(
            file=match.group("file"),
            line=int(match.group("line")),
            column=int(match.group("col")),
        ),
    )


def _ty_summary_findings(text: str) -> list[Finding]:
    if not re.search(r"Found \d+ diagnostics", text):
        return []
    return [
        Finding(
            rule_id="ty",
            severity=Severity.ERROR,
            message=text.strip().splitlines()[-1],
        )
    ]


def parse_bandit(stdout: str) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    findings: list[Finding] = []
    for item in payload.get("results", []):
        findings.append(
            Finding(
                rule_id=item.get("test_id", "bandit"),
                severity=Severity.ERROR
                if item.get("issue_severity") == "HIGH"
                else Severity.WARNING,
                message=item.get("issue_text", "bandit finding"),
                location=Location(
                    file=item.get("filename", ""),
                    line=item.get("line_number"),
                ),
            )
        )
    return findings


def parse_radon_cc(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    max_value = _policy_max_rank_value(check)
    findings: list[Finding] = []
    for file_path, blocks in payload.items():
        findings.extend(_radon_cc_file_findings(file_path, blocks, max_value))
    return findings


def parse_radon_mi(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    max_value = _policy_max_rank_value(check)
    findings: list[Finding] = []
    for file_path, item in payload.items():
        finding = _radon_mi_file_finding(file_path, item, max_value)
        if finding is not None:
            findings.append(finding)
    return findings


def _policy_max_rank_value(check: CheckDef) -> int:
    max_rank = (check.policy.max_complexity_rank if check.policy else "A") or "A"
    return RANK_ORDER.get(max_rank, 1)


def _radon_cc_file_findings(file_path: str, blocks: list[dict], max_value: int) -> list[Finding]:
    findings: list[Finding] = []
    for block in blocks:
        finding = _radon_cc_block_finding(file_path, block, max_value)
        if finding is not None:
            findings.append(finding)
    return findings


def _radon_cc_block_finding(file_path: str, block: dict, max_value: int) -> Finding | None:
    rank = block.get("rank", "A")
    if RANK_ORDER.get(rank, 99) <= max_value:
        return None
    return Finding(
        rule_id="complexity",
        severity=Severity.ERROR,
        message=f"{block.get('type')} {block.get('name')} complexity rank {rank}",
        location=Location(file=file_path, line=block.get("lineno")),
    )


def _radon_mi_file_finding(file_path: str, item: dict, max_value: int) -> Finding | None:
    rank = item.get("rank", "A")
    if RANK_ORDER.get(rank, 99) <= max_value:
        return None
    return Finding(
        rule_id="maintainability",
        severity=Severity.ERROR,
        message=f"Maintainability index rank {rank} (mi={item.get('mi')})",
        location=Location(file=file_path),
    )


def parse_jscpd(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    threshold = check.policy.max_duplication_percent if check.policy else None
    if threshold is not None:
        return _jscpd_threshold_findings(payload, threshold)
    return _jscpd_duplicate_findings(payload)


def _jscpd_threshold_findings(payload: dict, threshold: float) -> list[Finding]:
    percentage = payload.get("statistics", {}).get("total", {}).get("percentage", 0)
    if percentage <= threshold:
        return []
    return [
        Finding(
            rule_id="duplication",
            severity=Severity.ERROR,
            message=f"Duplication {percentage}% exceeds threshold {threshold}%",
        )
    ]


def _jscpd_duplicate_findings(payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for duplicate in payload.get("duplicates", []):
        first = duplicate.get("firstFile", {})
        second = duplicate.get("secondFile", {})
        findings.append(
            Finding(
                rule_id="duplicate-block",
                severity=Severity.WARNING,
                message=f"Duplicated block ({duplicate.get('lines', 0)} lines, {duplicate.get('format', '')})",
                location=Location(
                    file=first.get("name", ""), line=first.get("startLoc", {}).get("line")
                ),
                snippet=f"also in {second.get('name', '')}",
            )
        )
    return findings


def parse_semgrep(stdout: str) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    findings: list[Finding] = []
    for item in payload.get("results", []):
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {})
        findings.append(
            Finding(
                rule_id=item.get("check_id", "semgrep"),
                severity=Severity.ERROR
                if extra.get("severity", "").upper() in {"ERROR", "HIGH"}
                else Severity.WARNING,
                message=extra.get("message", metadata.get("message", "semgrep finding")),
                location=Location(
                    file=item.get("path", ""),
                    line=item.get("start", {}).get("line"),
                    column=item.get("start", {}).get("col"),
                    end_line=item.get("end", {}).get("line"),
                    end_column=item.get("end", {}).get("col"),
                ),
                snippet=extra.get("lines"),
            )
        )
    return findings


def parse_deadcode(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings = [
        finding
        for line in text.splitlines()
        if (finding := _deadcode_line_finding(line)) is not None
    ]
    if findings:
        return findings
    return _deadcode_fallback(text)


_DEADCODE_PATTERN = re.compile(
    r"(?P<file>[^:]+):(?P<line>\d+):\s*(?P<code>DC\d+):\s*(?P<message>.+)"
)


def _deadcode_line_finding(line: str) -> Finding | None:
    match = _DEADCODE_PATTERN.search(line)
    if not match:
        return None
    return Finding(
        rule_id=match.group("code"),
        severity=Severity.ERROR,
        message=match.group("message").strip(),
        location=Location(file=match.group("file"), line=int(match.group("line"))),
    )


def _deadcode_fallback(text: str) -> list[Finding]:
    if not re.search(r"DC\d+", text):
        return []
    return [Finding(rule_id="deadcode", severity=Severity.ERROR, message=text.strip()[:500])]


def parse_vulture(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<confidence>\d+)%\s*confidence:\s*(?P<message>.+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                Finding(
                    rule_id="vulture",
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                    ),
                )
            )
    return findings


def parse_pydeps_cycles(stdout: str, stderr: str) -> list[Finding]:
    text = _stdout_or_stderr(stdout, stderr).strip()
    if not text:
        return []
    if "No import cycles detected" in text:
        return []
    return _pydeps_cycle_findings(text)


def _stdout_or_stderr(stdout: str, stderr: str) -> str:
    if stdout:
        return stdout
    return stderr


def _pydeps_cycle_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in text.splitlines():
        message = _pydeps_cycle_message(line)
        if message is None:
            continue
        findings.append(Finding(rule_id="import-cycle", severity=Severity.ERROR, message=message))
    return findings


def _pydeps_cycle_message(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if "No import cycles" in stripped:
        return None
    return stripped


def parse_pytest(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings = _pytest_line_findings(text)
    if findings:
        return findings
    return _pytest_summary_findings(text)


_FAIL_PATTERN = re.compile(r"^(?P<file>[^\s]+):(?P<line>\d+):\s*(?P<message>.+)$")


def _pytest_line_findings(text: str) -> list[Finding]:
    return [
        finding for line in text.splitlines() if (finding := _pytest_line_finding(line)) is not None
    ]


def _pytest_line_finding(line: str) -> Finding | None:
    if _is_pytest_failed_line(line):
        return Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip())
    return _pytest_location_finding(line)


def _is_pytest_failed_line(line: str) -> bool:
    return line.startswith("FAILED ") or " FAILED" in line


def _pytest_location_finding(line: str) -> Finding | None:
    match = _FAIL_PATTERN.match(line.strip())
    if not match:
        return None
    message = match.group("message")
    if not _looks_like_pytest_error(message):
        return None
    return Finding(
        rule_id="pytest",
        severity=Severity.ERROR,
        message=message.strip(),
        location=Location(file=match.group("file"), line=int(match.group("line"))),
    )


def _looks_like_pytest_error(message: str) -> bool:
    lowered = message.lower()
    return "error" in lowered or "failed" in lowered


def _pytest_summary_findings(text: str) -> list[Finding]:
    summary = [
        line for line in text.splitlines() if "failed" in line.lower() or "error" in line.lower()
    ]
    return [
        Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip())
        for line in summary[-3:]
    ]
