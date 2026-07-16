"""Analysis-tool parsers."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from pyossmtool.models import CheckDef, Finding, Location, Severity
from pyossmtool.parsers.base import Parser, register
from pyossmtool.parsers.common import RANK_ORDER
from pyossmtool.parsers.patterns import JsonListParser, LineRegexParser, PolicyJsonParser


def _policy_max_rank_value(check: CheckDef) -> int:
    max_rank = (check.policy.max_complexity_rank if check.policy else "A") or "A"
    return RANK_ORDER.get(max_rank, 1)


@register
class BanditParser(JsonListParser):
    """Bandit emits ``{\"results\": [...]}`` rather than a bare JSON array."""

    id = "bandit_json"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        if not stdout.strip():
            return []
        payload = json.loads(stdout)
        findings: list[Finding] = []
        for item in payload.get("results", []):
            finding = self.map_item(item)
            if finding is not None:
                findings.append(finding)
        return findings

    def map_item(self, item: dict) -> Finding:
        return Finding(
            rule_id=item.get("test_id", "bandit"),
            severity=Severity.ERROR if item.get("issue_severity") == "HIGH" else Severity.WARNING,
            message=item.get("issue_text", "bandit finding"),
            location=Location(
                file=item.get("filename", ""),
                line=item.get("line_number"),
            ),
        )


@register
class TyParser(LineRegexParser):
    id = "ty_concise"
    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<kind>\w+):\s*(?P<message>.+)$"
    )

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        findings = super().parse(stdout, stderr, check=check)
        if findings:
            return findings
        return self._summary_findings(stdout or stderr)

    def map_match(self, match: re.Match[str]) -> Finding:
        return Finding(
            rule_id=match.group("kind"),
            severity=Severity.ERROR,
            message=match.group("message"),
            location=Location(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
            ),
        )

    def _summary_findings(self, text: str) -> list[Finding]:
        if not re.search(r"Found \d+ diagnostics", text):
            return []
        return [
            Finding(
                rule_id="ty",
                severity=Severity.ERROR,
                message=text.strip().splitlines()[-1],
            )
        ]


@register
class RadonCcParser(PolicyJsonParser):
    id = "radon_cc_json"

    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        max_value = _policy_max_rank_value(check)
        findings: list[Finding] = []
        for file_path, blocks in payload.items():
            findings.extend(self._file_findings(file_path, blocks, max_value))
        return findings

    def _file_findings(self, file_path: str, blocks: list[dict], max_value: int) -> list[Finding]:
        findings: list[Finding] = []
        for block in blocks:
            finding = self._block_finding(file_path, block, max_value)
            if finding is not None:
                findings.append(finding)
        return findings

    def _block_finding(self, file_path: str, block: dict, max_value: int) -> Finding | None:
        rank = block.get("rank", "A")
        if RANK_ORDER.get(rank, 99) <= max_value:
            return None
        return Finding(
            rule_id="complexity",
            severity=Severity.ERROR,
            message=f"{block.get('type')} {block.get('name')} complexity rank {rank}",
            location=Location(file=file_path, line=block.get("lineno")),
        )


@register
class RadonMiParser(PolicyJsonParser):
    id = "radon_mi_json"

    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        max_value = _policy_max_rank_value(check)
        findings: list[Finding] = []
        for file_path, item in payload.items():
            finding = self._file_finding(file_path, item, max_value)
            if finding is not None:
                findings.append(finding)
        return findings

    def _file_finding(self, file_path: str, item: dict, max_value: int) -> Finding | None:
        rank = item.get("rank", "A")
        if RANK_ORDER.get(rank, 99) <= max_value:
            return None
        return Finding(
            rule_id="maintainability",
            severity=Severity.ERROR,
            message=f"Maintainability index rank {rank} (mi={item.get('mi')})",
            location=Location(file=file_path),
        )


@register
class JscpdParser(PolicyJsonParser):
    id = "jscpd_json"

    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        threshold = check.policy.max_duplication_percent if check.policy else None
        if threshold is not None:
            return self._threshold_findings(payload, threshold)
        return self._duplicate_findings(payload)

    def _threshold_findings(self, payload: dict, threshold: float) -> list[Finding]:
        percentage = payload.get("statistics", {}).get("total", {}).get("percentage", 0)
        if percentage <= threshold:
            return []
        return [
            Finding(
                rule_id="duplication",
                severity=Severity.ERROR,
                message=f"Duplication {percentage}% exceeds threshold {threshold}%",
            )
        ]

    def _duplicate_findings(self, payload: dict) -> list[Finding]:
        findings: list[Finding] = []
        for duplicate in payload.get("duplicates", []):
            first = duplicate.get("firstFile", {})
            second = duplicate.get("secondFile", {})
            findings.append(
                Finding(
                    rule_id="duplicate-block",
                    severity=Severity.WARNING,
                    message=(f"Duplicated block ({duplicate.get('lines', 0)} lines, {duplicate.get('format', '')})"),
                    location=Location(file=first.get("name", ""), line=first.get("startLoc", {}).get("line")),
                    snippet=f"also in {second.get('name', '')}",
                )
            )
        return findings


@register
class SemgrepParser(Parser):
    id = "semgrep_json"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        if not stdout.strip():
            return []
        payload = json.loads(stdout)
        findings: list[Finding] = []
        for item in payload.get("results", []):
            findings.append(self._item_finding(item))
        return findings

    def _item_finding(self, item: dict) -> Finding:
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {})
        return Finding(
            rule_id=item.get("check_id", "semgrep"),
            severity=Severity.ERROR if extra.get("severity", "").upper() in {"ERROR", "HIGH"} else Severity.WARNING,
            message=extra.get("message", metadata.get("message", "semgrep finding")),
            location=Location(
                file=item.get("path", ""),
                line=item.get("start", {}).get("line"),
                column=item.get("start", {}).get("col"),
                end_line=item.get("end", {}).get("line"),
                end_column=item.get("end", {}).get("col"),
            ),
            snippet=extra.get("lines"),
        )


@register
class DeadcodeParser(Parser):
    id = "deadcode_text"
    _pattern = re.compile(r"(?P<file>[^:]+):(?P<line>\d+):\s*(?P<code>DC\d+):\s*(?P<message>.+)")

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = stdout or stderr
        findings = [finding for line in text.splitlines() if (finding := self._line_finding(line)) is not None]
        if findings:
            return findings
        return self._fallback(text)

    def _line_finding(self, line: str) -> Finding | None:
        match = self._pattern.search(line)
        if not match:
            return None
        return Finding(
            rule_id=match.group("code"),
            severity=Severity.ERROR,
            message=match.group("message").strip(),
            location=Location(file=match.group("file"), line=int(match.group("line"))),
        )

    def _fallback(self, text: str) -> list[Finding]:
        if not re.search(r"DC\d+", text):
            return []
        return [Finding(rule_id="deadcode", severity=Severity.ERROR, message=text.strip()[:500])]


@register
class VultureParser(LineRegexParser):
    id = "vulture_text"
    pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<confidence>\d+)%\s*confidence:\s*(?P<message>.+)$"
    )

    def map_match(self, match: re.Match[str]) -> Finding:
        return Finding(
            rule_id="vulture",
            severity=Severity.ERROR,
            message=match.group("message").strip(),
            location=Location(
                file=match.group("file"),
                line=int(match.group("line")),
            ),
        )


@register
class PydepsCyclesParser(Parser):
    id = "pydeps_cycles_text"

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout if stdout else stderr).strip()
        if not text:
            return []
        if "No import cycles detected" in text:
            return []
        return self._cycle_findings(text)

    def _cycle_findings(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for line in text.splitlines():
            message = self._cycle_message(line)
            if message is None:
                continue
            findings.append(Finding(rule_id="import-cycle", severity=Severity.ERROR, message=message))
        return findings

    def _cycle_message(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped:
            return None
        if "No import cycles" in stripped:
            return None
        return stripped


@register
class PytestParser(Parser):
    id = "pytest_text"
    _fail_pattern = re.compile(r"^(?P<file>[^\s]+):(?P<line>\d+):\s*(?P<message>.+)$")

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text:
            return []
        findings = self._line_findings(text)
        if findings:
            return findings
        return self._summary_findings(text)

    def _line_findings(self, text: str) -> list[Finding]:
        return [finding for line in text.splitlines() if (finding := self._line_finding(line)) is not None]

    def _line_finding(self, line: str) -> Finding | None:
        if line.startswith("FAILED ") or " FAILED" in line:
            return Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip())
        return self._location_finding(line)

    def _location_finding(self, line: str) -> Finding | None:
        match = self._fail_pattern.match(line.strip())
        if not match:
            return None
        message = match.group("message")
        lowered = message.lower()
        if "error" not in lowered and "failed" not in lowered:
            return None
        return Finding(
            rule_id="pytest",
            severity=Severity.ERROR,
            message=message.strip(),
            location=Location(file=match.group("file"), line=int(match.group("line"))),
        )

    def _summary_findings(self, text: str) -> list[Finding]:
        summary = [line for line in text.splitlines() if "failed" in line.lower() or "error" in line.lower()]
        return [Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip()) for line in summary[-3:]]
