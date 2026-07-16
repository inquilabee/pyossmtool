"""Gate / script / CLI text parsers."""

from __future__ import annotations

import json
import re

from pyaitools.models import CheckDef, Finding, Severity
from pyaitools.parsers.base import Parser, register
from pyaitools.parsers.common import finding_from_dict


@register
class CliTextParser(Parser):
    id = "cli_text"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        return self._findings(text)

    def _findings(self, text: str) -> list[Finding]:
        return [
            Finding(rule_id="check", severity=Severity.ERROR, message=line.strip())
            for line in text.splitlines()
            if line.strip()
        ]


@register
class ScriptTextParser(Parser):
    id = "script_text"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        findings: list[Finding] = []
        for line in (stdout or stderr).splitlines():
            finding = self._fail_finding(line)
            if finding is not None:
                findings.append(finding)
        return findings

    def _fail_finding(self, line: str) -> Finding | None:
        stripped = line.strip()
        if not stripped:
            return None
        message = self._fail_message(stripped)
        if message is None:
            return None
        return Finding(rule_id="gate", severity=Severity.ERROR, message=message)

    def _fail_message(self, stripped: str) -> str | None:
        if stripped.startswith("FAIL "):
            return stripped.removeprefix("FAIL ").strip()
        if stripped.startswith("FAIL:"):
            return stripped.removeprefix("FAIL:").strip()
        if re.match(r"^FAIL\b", stripped):
            return stripped
        return None


@register
class GateJsonParser(Parser):
    id = "gate_json"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = stdout.strip()
        if not text:
            return ScriptTextParser().parse(stdout, stderr)
        return self._from_text(text, stdout, stderr)

    def _from_text(self, text: str, stdout: str, stderr: str) -> list[Finding]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return ScriptTextParser().parse(stdout, stderr)
        return [finding_from_dict(item) for item in self._items(payload) if isinstance(item, dict)]

    def _items(self, payload) -> list:
        if isinstance(payload, dict) and "findings" in payload:
            return payload["findings"]
        if isinstance(payload, list):
            return payload
        return []


@register
class NoopParser(Parser):
    id = "noop"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        return []
