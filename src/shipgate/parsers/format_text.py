"""Markdown and YAML format parsers."""

from __future__ import annotations

import re
from pathlib import Path

from shipgate.models import CheckDef, Finding, FixHint, Location, Severity
from shipgate.parsers.base import Parser, register
from shipgate.parsers.patterns import FallbackTextParser


@register
class MdformatParser(FallbackTextParser):
    id = "mdformat_text"
    _quoted_path = re.compile(r'"([^"]+\.md)"')
    _error_file_block = re.compile(
        r'Error:\s*File\s*"([^"]+\.md)"\s*is not formatted\.?',
        re.IGNORECASE | re.DOTALL,
    )

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        block_findings = self._error_file_findings(text)
        if block_findings:
            return block_findings
        findings = self._line_findings(text)
        if findings:
            return findings
        return [self._fallback_finding(text)]

    def _error_file_findings(self, text: str) -> list[Finding]:
        return [
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message=f"{Path(match.group(1)).name} is not formatted",
                location=Location(file=match.group(1)),
                fix=FixHint(description="Run mdformat", command=f"mdformat {match.group(1)}"),
            )
            for match in self._error_file_block.finditer(text)
        ]

    def _line_findings(self, text: str) -> list[Finding]:
        return [self._line_finding(line) for line in text.splitlines() if self._line_match(line)]

    def _line_match(self, line: str) -> bool:
        lowered = line.lower()
        if "would be reformatted" in lowered:
            return True
        if "failed" in lowered:
            return True
        if self._quoted_path.search(line):
            return True
        return line.strip().endswith(".md")

    def _line_finding(self, line: str) -> Finding:
        file_path = self._extract_path(line)
        return Finding(
            rule_id="format",
            severity=Severity.ERROR,
            message=self._line_message(line, file_path),
            location=Location(file=file_path) if file_path else None,
            fix=self._mdformat_fix(file_path),
        )

    def _extract_path(self, text: str) -> str | None:
        path_match = self._quoted_path.search(text)
        return path_match.group(1) if path_match else None

    def _line_message(self, line: str, file_path: str | None) -> str:
        message = line.strip() or "Markdown would be reformatted"
        if file_path and "is not formatted" in message.lower():
            return f"{Path(file_path).name} is not formatted"
        return message

    @staticmethod
    def _mdformat_fix(file_path: str | None) -> FixHint:
        command = f"mdformat {file_path}" if file_path else "mdformat ."
        return FixHint(description="Run mdformat", command=command)

    def _fallback_finding(self, text: str) -> Finding:
        file_path = self._extract_path(text)
        if file_path:
            return Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message=f"{Path(file_path).name} is not formatted",
                location=Location(file=file_path),
                fix=FixHint(description="Run mdformat", command=f"mdformat {file_path}"),
            )
        message = text.splitlines()[-1] if text else "Markdown formatting check failed"
        return Finding(rule_id="format", severity=Severity.ERROR, message=message)


@register
class YamlfmtParser(Parser):
    id = "yamlfmt_text"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
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
