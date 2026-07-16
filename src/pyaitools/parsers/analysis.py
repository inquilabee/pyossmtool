"""Analysis-tool parsers (bandit and more)."""

from __future__ import annotations

import json

from pyaitools.models import CheckDef, Finding, Location, Severity
from pyaitools.parsers.base import register
from pyaitools.parsers.patterns import JsonListParser


@register
class BanditParser(JsonListParser):
    """Bandit emits ``{\"results\": [...]}`` rather than a bare JSON array."""

    id = "bandit_json"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        if not stdout.strip():
            return []
        payload = json.loads(stdout)
        findings: list[Finding] = []
        for item in payload.get("results", []):
            finding = self.parse_one(item)
            if finding is not None:
                findings.append(finding)
        return findings

    def parse_one(self, item: dict) -> Finding:
        return Finding(
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
