"""Markdown and YAML format parsers."""

from __future__ import annotations

from pyaitools.models import CheckDef, Finding, FixHint, Severity
from pyaitools.parsers.base import Parser, register
from pyaitools.parsers.patterns import FallbackTextParser


@register
class MdformatParser(FallbackTextParser):
    id = "mdformat_text"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        findings = self._line_findings(text)
        if findings:
            return findings
        return [self._fallback_finding(text)]

    def _line_findings(self, text: str) -> list[Finding]:
        return [self._line_finding(line) for line in text.splitlines() if self._line_match(line)]

    def _line_match(self, line: str) -> bool:
        lowered = line.lower()
        if "would be reformatted" in lowered:
            return True
        if "failed" in lowered:
            return True
        return line.endswith(".md")

    def _line_finding(self, line: str) -> Finding:
        return Finding(
            rule_id="format",
            severity=Severity.ERROR,
            message=line.strip() or "Markdown would be reformatted",
            fix=FixHint(description="Run mdformat", command="mdformat ."),
        )

    def _fallback_finding(self, text: str) -> Finding:
        message = text.splitlines()[-1] if text else "Markdown formatting check failed"
        return Finding(rule_id="format", severity=Severity.ERROR, message=message)


@register
class YamlfmtParser(Parser):
    id = "yamlfmt_text"

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        return self._findings(text)

    def _findings(self, text: str) -> list[Finding]:
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
