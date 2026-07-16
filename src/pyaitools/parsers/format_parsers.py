"""Tool output parsers."""

from __future__ import annotations

import json

from pyaitools.models import Finding, FixHint, Location, Severity
from pyaitools.parsers.common import strip_ansi


def parse_shellcheck(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    payload = json.loads(payload_text)
    return [_shellcheck_finding(item) for item in payload]


def _shellcheck_finding(item: dict) -> Finding:
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


def parse_shfmt_diff(stdout: str, stderr: str) -> list[Finding]:
    text = strip_ansi(stdout or stderr)
    if not text.strip():
        return []
    findings = _collect_shfmt_findings(text.splitlines())
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


def _collect_shfmt_findings(lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    current_file: str | None = None
    for line in lines:
        current_file = _shfmt_file_from_diff_line(line, current_file)
        finding = _shfmt_diff_finding(line, current_file)
        if finding is not None:
            findings.append(finding)
    return findings


def _shfmt_file_from_diff_line(line: str, current_file: str | None) -> str | None:
    if not line.startswith(("--- ", "+++ ")):
        return current_file
    marker = line[4:].split("\t")[0].strip()
    if marker and marker != "/dev/null":
        return marker
    return current_file


def _shfmt_diff_finding(line: str, current_file: str | None) -> Finding | None:
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


def parse_mdformat(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings = _mdformat_line_findings(text)
    if findings:
        return findings
    return [_mdformat_fallback_finding(text)]


def _mdformat_line_findings(text: str) -> list[Finding]:
    return [
        _mdformat_line_finding(line) for line in text.splitlines() if _mdformat_line_match(line)
    ]


def _mdformat_line_match(line: str) -> bool:
    lowered = line.lower()
    if "would be reformatted" in lowered:
        return True
    if "failed" in lowered:
        return True
    return line.endswith(".md")


def _mdformat_fallback_finding(text: str) -> Finding:
    message = text.splitlines()[-1] if text else "Markdown formatting check failed"
    return Finding(rule_id="format", severity=Severity.ERROR, message=message)


def _mdformat_line_finding(line: str) -> Finding:
    return Finding(
        rule_id="format",
        severity=Severity.ERROR,
        message=line.strip() or "Markdown would be reformatted",
        fix=FixHint(description="Run mdformat", command="mdformat ."),
    )


def parse_yamlfmt(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    return [
        Finding(
            rule_id="format",
            severity=Severity.ERROR,
            message=line.strip(),
            fix=FixHint(description="Run yamlfmt", command="yamlfmt ."),
        )
        for line in text.splitlines()
        if line.strip()
    ]
