"""Tool output parsers."""

from __future__ import annotations

import json
import re

from pyaitools.models import Finding, Severity
from pyaitools.parsers.common import finding_from_dict


def parse_cli_text(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    return [
        Finding(rule_id="check", severity=Severity.ERROR, message=line.strip())
        for line in text.splitlines()
        if line.strip()
    ]


def parse_gate_json(stdout: str, stderr: str) -> list[Finding]:
    text = stdout.strip()
    if not text:
        return parse_script_text(stdout, stderr)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return parse_script_text(stdout, stderr)
    return [finding_from_dict(item) for item in _gate_json_items(payload) if isinstance(item, dict)]


def _gate_json_items(payload) -> list:
    if isinstance(payload, dict) and "findings" in payload:
        return payload["findings"]
    if isinstance(payload, list):
        return payload
    return []


def parse_script_text(stdout: str, stderr: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in (stdout or stderr).splitlines():
        finding = _script_fail_finding(line)
        if finding is not None:
            findings.append(finding)
    return findings


def _script_fail_finding(line: str) -> Finding | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("FAIL "):
        return Finding(
            rule_id="gate",
            severity=Severity.ERROR,
            message=stripped.removeprefix("FAIL ").strip(),
        )
    if stripped.startswith("FAIL:"):
        return Finding(
            rule_id="gate",
            severity=Severity.ERROR,
            message=stripped.removeprefix("FAIL:").strip(),
        )
    if re.match(r"^FAIL\b", stripped):
        return Finding(rule_id="gate", severity=Severity.ERROR, message=stripped)
    return None
