"""Shared parser pattern bases."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from pyaitools.models import CheckDef, Finding
from pyaitools.parsers.base import Parser


class JsonListParser(Parser):
    """JSON array in stdout (or stderr if stdout empty) → parse_one per item."""

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        payload = json.loads(payload_text)
        findings: list[Finding] = []
        for item in payload:
            finding = self.parse_one(item)
            if finding is not None:
                findings.append(finding)
        return findings


class LineRegexParser(Parser):
    pattern: ClassVar[re.Pattern[str]]

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = stdout or stderr
        findings: list[Finding] = []
        for line in text.splitlines():
            match = self.pattern.match(line.strip())
            if not match:
                continue
            finding = self.parse_one(match)
            if finding is not None:
                findings.append(finding)
        return findings


class DiffTextParser(Parser):
    """Override parse(); subclasses implement format-diff scanning."""

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError


class PolicyJsonParser(Parser):
    needs_check: ClassVar[bool] = True

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        if check is None:
            raise ValueError(f"{self.id} requires check")
        if not stdout.strip():
            return []
        return self.parse_payload(json.loads(stdout), check)

    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        raise NotImplementedError


class FallbackTextParser(Parser):
    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError
