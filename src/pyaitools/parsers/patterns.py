"""Shared parser pattern bases."""

from __future__ import annotations

import json
import re
from abc import abstractmethod
from typing import Any, ClassVar

from pyaitools.models import CheckDef, Finding
from pyaitools.parsers.base import Parser


class JsonListParser(Parser):
    """JSON array in stdout (or stderr if stdout empty) → map_item per entry."""

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        return self._map_items(json.loads(payload_text))

    def _map_items(self, payload: list) -> list[Finding]:
        findings: list[Finding] = []
        for item in payload:
            finding = self.map_item(item)
            if finding is not None:
                findings.append(finding)
        return findings

    @abstractmethod
    def map_item(self, item: Any) -> Finding | None:
        raise NotImplementedError


class LineRegexParser(Parser):
    pattern: ClassVar[re.Pattern[str]]

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        return self._map_lines(stdout or stderr)

    def _map_lines(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for line in text.splitlines():
            match = self.pattern.match(line.strip())
            if not match:
                continue
            finding = self.map_match(match)
            if finding is not None:
                findings.append(finding)
        return findings

    @abstractmethod
    def map_match(self, match: re.Match[str]) -> Finding | None:
        raise NotImplementedError


class DiffTextParser(Parser):
    """Subclasses implement format-diff scanning in parse()."""


class PolicyJsonParser(Parser):
    needs_check: ClassVar[bool] = True

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        if check is None:
            raise ValueError(f"{self.id} requires check")
        if not stdout.strip():
            return []
        return self.parse_payload(json.loads(stdout), check)

    @abstractmethod
    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        raise NotImplementedError


class FallbackTextParser(Parser):
    """Subclasses implement free-form text parsing in parse()."""
