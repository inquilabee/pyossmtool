"""Analysis-tool parsers."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from shipgate.models import CheckDef, Finding, Location, Severity
from shipgate.parsers.base import Parser, register
from shipgate.parsers.common import RANK_ORDER
from shipgate.parsers.patterns import JsonListParser, LineRegexParser, PolicyJsonParser
from shipgate.paths import normalize_finding_path


def _policy_max_rank_value(check: CheckDef) -> int:
    max_rank = (check.policy.max_complexity_rank if check.policy else "A") or "A"
    return RANK_ORDER.get(max_rank, 1)


def _first_stripped_line(text: str, default: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), default)


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
        file_path = normalize_finding_path(item.get("filename") or None)
        return Finding(
            rule_id=item.get("test_id", "bandit"),
            severity=Severity.ERROR if item.get("issue_severity") == "HIGH" else Severity.WARNING,
            message=item.get("issue_text", "bandit finding"),
            location=Location(
                file=file_path or "",
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
            location=Location(file=normalize_finding_path(file_path) or file_path, line=block.get("lineno")),
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
            location=Location(file=normalize_finding_path(file_path) or file_path),
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
        findings = [
            Finding(
                rule_id="duplication",
                severity=Severity.ERROR,
                message=f"Duplication {percentage}% exceeds threshold {threshold}%",
            )
        ]
        findings.extend(self._duplicate_findings(payload))
        return findings

    def _duplicate_findings(self, payload: dict) -> list[Finding]:
        return [self._duplicate_finding(duplicate) for duplicate in payload.get("duplicates", [])]

    def _duplicate_finding(self, duplicate: dict) -> Finding:
        first = duplicate.get("firstFile", {})
        second = duplicate.get("secondFile", {})
        file_path = normalize_finding_path(first.get("name") or None) or ""
        second_name = normalize_finding_path(second.get("name") or None) or second.get("name", "")
        return Finding(
            rule_id="duplicate-block",
            severity=Severity.WARNING,
            message=(f"Duplicated block ({duplicate.get('lines', 0)} lines, {duplicate.get('format', '')})"),
            location=Location(file=file_path, line=first.get("startLoc", {}).get("line")),
            snippet=f"also in {second_name}",
        )


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
    # deadcode v2: file:line:col: DCxx message  (colon after code is optional)
    _pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+)(?::(?P<column>\d+))?:\s*"
        r"(?P<code>DC\d+)\s*:?\s*(?P<message>.+)$"
    )

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = stdout or stderr
        findings = [finding for line in text.splitlines() if (finding := self._line_finding(line)) is not None]
        if findings:
            return findings
        return self._fallback(text)

    def _line_finding(self, line: str) -> Finding | None:
        match = self._pattern.search(line.strip())
        if not match:
            return None
        column = match.group("column")
        file_path = normalize_finding_path(match.group("file")) or match.group("file")
        return Finding(
            rule_id=match.group("code"),
            severity=Severity.ERROR,
            message=match.group("message").strip(),
            location=Location(
                file=file_path,
                line=int(match.group("line")),
                column=int(column) if column is not None else None,
            ),
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

    _NON_CYCLE_PREFIXES: ClassVar[tuple[str, ...]] = ("usage:", "[-", "--", "pydeps: error:")

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        text = (stdout or stderr).strip()
        if not text or "No import cycles detected" in text:
            return []
        return self._classify(text)

    def _classify(self, text: str) -> list[Finding]:
        cli_error = self._cli_error_finding(text)
        if cli_error is not None:
            return [cli_error]
        analysis_error = self._analysis_error_finding(text)
        if analysis_error is not None:
            return [analysis_error]
        cycles = self._cycle_findings(text)
        if cycles:
            return cycles
        message = _first_stripped_line(text, "pydeps failed")
        return [Finding(rule_id="pydeps-error", severity=Severity.ERROR, message=message)]

    def _cli_error_finding(self, text: str) -> Finding | None:
        """Collapse argparse usage dumps into one actionable finding."""
        error_line, saw_usage = self._scan_cli_error(text)
        if error_line is not None:
            return Finding(rule_id="pydeps-error", severity=Severity.ERROR, message=error_line)
        if saw_usage:
            return Finding(
                rule_id="pydeps-error",
                severity=Severity.ERROR,
                message="pydeps failed (check target is a package/directory, not a file list)",
            )
        return None

    def _scan_cli_error(self, text: str) -> tuple[str | None, bool]:
        error_line: str | None = None
        saw_usage = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("pydeps: error:"):
                error_line = stripped.removeprefix("pydeps: error:").strip() or stripped
            elif stripped.lower().startswith("usage: pydeps"):
                saw_usage = True
        return error_line, saw_usage

    def _analysis_error_finding(self, text: str) -> Finding | None:
        """Collapse pydeps module-name / analysis essays into one finding."""
        markers = (
            "Cannot analyze",
            "is not a valid Python module name",
            "Technical reason:",
        )
        if not any(marker in text for marker in markers):
            return None
        return Finding(rule_id="pydeps-error", severity=Severity.ERROR, message=self._analysis_message(text))

    def _analysis_message(self, text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Cannot analyze") or "is not a valid Python module name" in stripped:
                return stripped
        return _first_stripped_line(text, "pydeps analysis failed")

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
        if not stripped or "No import cycles" in stripped or "->" not in stripped:
            return None
        if stripped.startswith(self._NON_CYCLE_PREFIXES):
            return None
        return stripped


@register
class PytestParser(Parser):
    id = "pytest_text"
    _fail_pattern = re.compile(r"^(?P<file>[^\s]+):(?P<line>\d+):\s*(?P<message>.+)$")
    _coverage_row = re.compile(r"^\S+.+\s+\d+\s+\d+\s+\d+%")

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
        findings = [f for line in text.splitlines() if (f := self._summary_line_finding(line)) is not None]
        return findings[-3:]

    def _summary_line_finding(self, line: str) -> Finding | None:
        stripped = line.strip()
        if self._is_summary_noise(stripped):
            return None
        if self._is_summary_failure(stripped):
            return Finding(rule_id="pytest", severity=Severity.ERROR, message=stripped)
        return None

    def _is_summary_noise(self, stripped: str) -> bool:
        if not stripped or stripped.startswith(("---", "TOTAL", "=")):
            return True
        return bool(self._coverage_row.match(stripped))

    def _is_summary_failure(self, stripped: str) -> bool:
        if stripped.startswith(("FAILED ", "ERROR ", "E   ", "F   ")):
            return True
        lowered = stripped.lower()
        return " failed" in lowered or lowered.startswith("failed ") or " error" in lowered
