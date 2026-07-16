"""Prose and misc linter parsers."""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from pyaitools.models import CheckDef, Finding, Location, Severity
from pyaitools.parsers.base import Parser, register
from pyaitools.parsers.gates import CliTextParser
from pyaitools.parsers.patterns import FallbackTextParser, LineRegexParser


def _load_json_or_none(payload_text: str) -> Any:
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return None


@register
class GitleaksParser(Parser):
    id = "gitleaks_json"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return CliTextParser().parse(stdout, stderr)
        return [self.map_item(item) for item in payload]

    def map_item(self, item: dict) -> Finding:
        return Finding(
            rule_id=item.get("RuleID", "gitleaks"),
            severity=Severity.ERROR,
            message=f"Secret detected: {item.get('Description', 'potential leak')}",
            location=Location(
                file=item.get("File", ""),
                line=item.get("StartLine"),
                end_line=item.get("EndLine"),
            ),
        )


@register
class CodespellParser(LineRegexParser):
    id = "codespell_text"
    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<wrong>[^=]+)\s*==>\s*(?P<right>[^\s]+)"
    )

    def map_match(self, match: re.Match[str]) -> Finding:
        return Finding(
            rule_id="spelling",
            severity=Severity.ERROR,
            message=f"{match.group('wrong').strip()} -> {match.group('right').strip()}",
            location=Location(file=match.group("file"), line=int(match.group("line"))),
        )


@register
class MarkdownlintParser(Parser):
    id = "markdownlint_json"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        payload = _load_json_or_none(payload_text)
        if payload is None:
            return CliTextParser().parse(stdout, stderr)
        return self._from_payload(payload)

    def _from_payload(self, payload: Any) -> list[Finding]:
        if isinstance(payload, list):
            return self._list_findings(payload)
        if isinstance(payload, dict):
            return self._dict_findings(payload)
        return []

    def _list_findings(self, payload: list) -> list[Finding]:
        findings: list[Finding] = []
        for item in payload:
            if isinstance(item, dict):
                file_path = item.get("fileName", item.get("file", ""))
                findings.append(self._item_finding(item, file_path))
        return findings

    def _dict_findings(self, payload: dict) -> list[Finding]:
        findings: list[Finding] = []
        for file_path, items in payload.items():
            for item in items:
                findings.append(self._item_finding(item, file_path))
        return findings

    def _item_finding(self, item: dict, file_path: str) -> Finding:
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


@register
class YamllintParser(LineRegexParser):
    id = "yamllint_text"
    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
        r"\[(?P<severity>error|warning)\]\s*(?P<message>.+)$"
    )

    def map_match(self, match: re.Match[str]) -> Finding | None:
        if match.group("severity") != "error":
            return None
        return Finding(
            rule_id="yamllint",
            severity=Severity.ERROR,
            message=match.group("message").strip(),
            location=Location(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
            ),
        )


@register
class HadolintParser(Parser):
    id = "hadolint_json"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        payload = _load_json_or_none(payload_text)
        if payload is None:
            return CliTextParser().parse(stdout, stderr)
        return [self.map_item(item) for item in payload]

    def map_item(self, item: dict) -> Finding:
        return Finding(
            rule_id=item.get("code", "hadolint"),
            severity=Severity.ERROR if item.get("level") == "error" else Severity.WARNING,
            message=item.get("message", "hadolint finding"),
            location=Location(file=item.get("file", ""), line=item.get("line")),
        )


@register
class MutmutParser(FallbackTextParser):
    id = "mutmut_text"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text or self._all_passed(text):
            return []
        return CliTextParser().parse(stdout, stderr)

    def _all_passed(self, text: str) -> bool:
        lowered = text.lower()
        return "passed" in lowered and "failed" not in lowered


@register
class SourceryParser(FallbackTextParser):
    id = "sourcery_text"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        return [
            Finding(rule_id="sourcery", severity=Severity.WARNING, message=message)
            for line in text.splitlines()
            if (message := self._message(line)) is not None
        ]

    def _message(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("reviewing"):
            return None
        return stripped
