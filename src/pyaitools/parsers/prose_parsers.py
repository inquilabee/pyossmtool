"""Tool output parsers."""

from __future__ import annotations

import json
import re

from pyaitools.models import Finding, Location, Severity
from pyaitools.parsers.gate_parsers import parse_cli_text


def parse_gitleaks(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return parse_cli_text(stdout, stderr)
    findings: list[Finding] = []
    for item in payload:
        findings.append(
            Finding(
                rule_id=item.get("RuleID", "gitleaks"),
                severity=Severity.ERROR,
                message=f"Secret detected: {item.get('Description', 'potential leak')}",
                location=Location(
                    file=item.get("File", ""),
                    line=item.get("StartLine"),
                    end_line=item.get("EndLine"),
                ),
            )
        )
    return findings


def parse_codespell(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<wrong>[^=]+)\s*==>\s*(?P<right>[^\s]+)"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                Finding(
                    rule_id="spelling",
                    severity=Severity.ERROR,
                    message=f"{match.group('wrong').strip()} -> {match.group('right').strip()}",
                    location=Location(file=match.group("file"), line=int(match.group("line"))),
                )
            )
    return findings


def parse_markdownlint(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    payload = _load_json_or_none(payload_text)
    if payload is None:
        return parse_cli_text(stdout, stderr)
    return _markdownlint_from_payload(payload)


def _load_json_or_none(payload_text: str):
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return None


def _markdownlint_from_payload(payload) -> list[Finding]:
    if isinstance(payload, list):
        return _markdownlint_list_findings(payload)
    if isinstance(payload, dict):
        return _markdownlint_dict_findings(payload)
    return []


def _markdownlint_item_finding(item: dict, file_path: str) -> Finding:
    rule_names = item.get("ruleNames")
    rule_id = rule_names[0] if rule_names else "markdownlint"
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        message=item.get("ruleDescription", item.get("ruleInformation", "markdownlint finding")),
        location=Location(
            file=file_path,
            line=item.get("lineNumber"),
            column=item.get("columnNumber"),
        ),
    )


def _markdownlint_list_findings(payload: list) -> list[Finding]:
    findings: list[Finding] = []
    for item in payload:
        if isinstance(item, dict):
            file_path = item.get("fileName", item.get("file", ""))
            findings.append(_markdownlint_item_finding(item, file_path))
    return findings


def _markdownlint_dict_findings(payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for file_path, items in payload.items():
        for item in items:
            findings.append(_markdownlint_item_finding(item, file_path))
    return findings


def parse_yamllint(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*\[(?P<severity>error|warning)\]\s*(?P<message>.+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match and match.group("severity") == "error":
            findings.append(
                Finding(
                    rule_id="yamllint",
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                        column=int(match.group("col")),
                    ),
                )
            )
    return findings


def parse_hadolint(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    payload = _load_json_or_none(payload_text)
    if payload is None:
        return parse_cli_text(stdout, stderr)
    return [_hadolint_finding(item) for item in payload]


def _hadolint_finding(item: dict) -> Finding:
    return Finding(
        rule_id=item.get("code", "hadolint"),
        severity=Severity.ERROR if item.get("level") == "error" else Severity.WARNING,
        message=item.get("message", "hadolint finding"),
        location=Location(file=item.get("file", ""), line=item.get("line")),
    )


def parse_mutmut(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    if "passed" in text.lower() and "failed" not in text.lower():
        return []
    return parse_cli_text(stdout, stderr)


def parse_sourcery(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    return [
        Finding(rule_id="sourcery", severity=Severity.WARNING, message=message)
        for line in text.splitlines()
        if (message := _sourcery_message(line)) is not None
    ]


def _sourcery_message(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.lower().startswith("reviewing"):
        return None
    return stripped
