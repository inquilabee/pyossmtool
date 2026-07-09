"""Parse native tool output into normalized Finding objects."""

from __future__ import annotations

import json
import re

from pyaitools.models import CheckDef, Finding, FixHint, Location, Severity


def parse_output(check: CheckDef, stdout: str, stderr: str) -> list[Finding]:
    parser = check.parser
    if parser == "ruff_json":
        return _parse_ruff_json(stdout)
    if parser == "ruff_format_text":
        return _parse_ruff_format(stdout, stderr)
    if parser == "ty_concise":
        return _parse_ty(stdout, stderr)
    if parser == "shellcheck_json":
        return _parse_shellcheck(stdout, stderr)
    if parser == "bandit_json":
        return _parse_bandit(stdout)
    if parser == "radon_cc_json":
        return _parse_radon_cc(stdout, check)
    if parser == "radon_mi_json":
        return _parse_radon_mi(stdout, check)
    if parser == "jscpd_json":
        return _parse_jscpd(stdout, check)
    if parser == "shfmt_diff":
        return _parse_shfmt_diff(stdout, stderr)
    if parser == "mdformat_text":
        return _parse_mdformat(stdout, stderr)
    if parser == "yamlfmt_text":
        return _parse_yamlfmt(stdout, stderr)
    if parser == "semgrep_json":
        return _parse_semgrep(stdout)
    if parser == "deadcode_text":
        return _parse_deadcode(stdout, stderr)
    if parser == "vulture_text":
        return _parse_vulture(stdout, stderr)
    if parser == "pydeps_cycles_text":
        return _parse_pydeps_cycles(stdout, stderr)
    if parser == "pytest_text":
        return _parse_pytest(stdout, stderr)
    if parser == "gitleaks_json":
        return _parse_gitleaks(stdout, stderr)
    if parser == "codespell_text":
        return _parse_codespell(stdout, stderr)
    if parser == "markdownlint_json":
        return _parse_markdownlint(stdout, stderr)
    if parser == "yamllint_text":
        return _parse_yamllint(stdout, stderr)
    if parser == "hadolint_json":
        return _parse_hadolint(stdout, stderr)
    if parser == "mutmut_text":
        return _parse_mutmut(stdout, stderr)
    if parser == "sourcery_text":
        return _parse_sourcery(stdout, stderr)
    if parser == "cli_text":
        return _parse_cli_text(stdout, stderr)
    if parser == "gate_json":
        return _parse_gate_json(stdout, stderr)
    if parser == "script_text":
        return _parse_script_text(stdout, stderr)
    if parser == "noop":
        return []
    raise ValueError(f"Unknown parser: {parser}")


def _parse_ruff_json(stdout: str) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    findings: list[Finding] = []
    for item in payload:
        location = None
        if item.get("filename"):
            location = Location(
                file=item["filename"],
                line=item.get("location", {}).get("row"),
                column=item.get("location", {}).get("column"),
                end_line=item.get("end_location", {}).get("row"),
                end_column=item.get("end_location", {}).get("column"),
            )
        findings.append(
            Finding(
                rule_id=item.get("code", "ruff"),
                severity=Severity.ERROR
                if item.get("code", "").startswith("E")
                else Severity.WARNING,
                message=item.get("message", "ruff finding"),
                location=location,
                snippet=item.get("message"),
                fix=FixHint(
                    description="Apply ruff auto-fix",
                    command=f"ruff check --fix {item.get('filename', '')}",
                )
                if item.get("filename")
                else None,
            )
        )
    return findings


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _parse_ruff_format(stdout: str, stderr: str) -> list[Finding]:
    text = _strip_ansi(stdout or stderr)
    if not text.strip():
        return []
    findings: list[Finding] = []
    current_file: str | None = None
    for line in text.splitlines():
        if line.endswith(".py") or line.endswith(".py would be reformatted"):
            current_file = _strip_ansi(line.split()[0].rstrip(":"))
            continue
        if line.startswith("Would reformat:"):
            current_file = line.split(":", 1)[1].strip()
            findings.append(
                Finding(
                    rule_id="format",
                    severity=Severity.ERROR,
                    message="File would be reformatted",
                    location=Location(file=current_file) if current_file else None,
                    fix=FixHint(
                        description="Run ruff format",
                        command=f"ruff format {current_file}" if current_file else "ruff format",
                    ),
                )
            )
        elif line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            if findings and current_file:
                findings[-1].snippet = (findings[-1].snippet or "") + line + "\n"
    if not findings and "reformatted" in text.lower():
        findings.append(
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message="Formatting differences detected",
                snippet=text[:500],
                fix=FixHint(description="Run ruff format", command="ruff format"),
            )
        )
    return findings


def _parse_ty(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<kind>\w+):\s*(?P<message>.+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                Finding(
                    rule_id=match.group("kind"),
                    severity=Severity.ERROR,
                    message=match.group("message"),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                        column=int(match.group("col")),
                    ),
                )
            )
    if not findings and re.search(r"Found \d+ diagnostics", text):
        findings.append(
            Finding(
                rule_id="ty",
                severity=Severity.ERROR,
                message=text.strip().splitlines()[-1],
            )
        )
    return findings


def _parse_shellcheck(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    payload = json.loads(payload_text)
    findings: list[Finding] = []
    for item in payload:
        level = item.get("level", "warning")
        severity = Severity.ERROR if level in {"error", "warning"} else Severity.INFO
        findings.append(
            Finding(
                rule_id=f"SC{item.get('code', 0)}",
                severity=severity,
                message=item.get("message", "shellcheck finding"),
                location=Location(
                    file=item.get("file", ""),
                    line=item.get("line"),
                    column=item.get("column"),
                    end_line=item.get("endLine"),
                    end_column=item.get("endColumn"),
                ),
            )
        )
    return findings


def _parse_bandit(stdout: str) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    findings: list[Finding] = []
    for item in payload.get("results", []):
        findings.append(
            Finding(
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
        )
    return findings


RANK_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}


def _parse_radon_cc(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    max_rank = (check.policy.max_complexity_rank if check.policy else "A") or "A"
    max_value = RANK_ORDER.get(max_rank, 1)
    findings: list[Finding] = []
    for file_path, blocks in payload.items():
        for block in blocks:
            rank = block.get("rank", "A")
            if RANK_ORDER.get(rank, 99) > max_value:
                findings.append(
                    Finding(
                        rule_id="complexity",
                        severity=Severity.ERROR,
                        message=f"{block.get('type')} {block.get('name')} complexity rank {rank}",
                        location=Location(file=file_path, line=block.get("lineno")),
                    )
                )
    return findings


def _parse_radon_mi(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    max_rank = (check.policy.max_complexity_rank if check.policy else "A") or "A"
    max_value = RANK_ORDER.get(max_rank, 1)
    findings: list[Finding] = []
    for file_path, item in payload.items():
        rank = item.get("rank", "A")
        if RANK_ORDER.get(rank, 99) > max_value:
            findings.append(
                Finding(
                    rule_id="maintainability",
                    severity=Severity.ERROR,
                    message=f"Maintainability index rank {rank} (mi={item.get('mi')})",
                    location=Location(file=file_path),
                )
            )
    return findings


def _parse_jscpd(stdout: str, check: CheckDef) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    threshold = check.policy.max_duplication_percent if check.policy else None
    findings: list[Finding] = []
    statistics = payload.get("statistics", {})
    total = statistics.get("total", {})
    percentage = total.get("percentage", 0)
    if threshold is not None:
        if percentage > threshold:
            findings.append(
                Finding(
                    rule_id="duplication",
                    severity=Severity.ERROR,
                    message=f"Duplication {percentage}% exceeds threshold {threshold}%",
                )
            )
        return findings

    duplicates = payload.get("duplicates", [])
    for duplicate in duplicates:
        first = duplicate.get("firstFile", {})
        second = duplicate.get("secondFile", {})
        findings.append(
            Finding(
                rule_id="duplicate-block",
                severity=Severity.WARNING,
                message=f"Duplicated block ({duplicate.get('lines', 0)} lines, {duplicate.get('format', '')})",
                location=Location(
                    file=first.get("name", ""), line=first.get("startLoc", {}).get("line")
                ),
                snippet=f"also in {second.get('name', '')}",
            )
        )
    return findings


def _parse_shfmt_diff(stdout: str, stderr: str) -> list[Finding]:
    text = _strip_ansi(stdout or stderr)
    if not text.strip():
        return []
    findings: list[Finding] = []
    current_file: str | None = None
    for line in text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            marker = line[4:].split("\t")[0].strip()
            if marker and marker != "/dev/null":
                current_file = marker
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("-") or line.startswith("+"):
            findings.append(
                Finding(
                    rule_id="format",
                    severity=Severity.ERROR,
                    message="Shell formatting difference",
                    location=Location(file=current_file) if current_file else None,
                    snippet=line[:200],
                    fix=FixHint(
                        description="Run shfmt -w",
                        command=f"shfmt -w {current_file}" if current_file else "shfmt -w",
                    ),
                )
            )
    if not findings and text.strip():
        findings.append(
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message="Shell formatting differences detected",
                snippet=text[:500],
            )
        )
    return findings


def _parse_mdformat(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        if (
            "would be reformatted" in line.lower()
            or "failed" in line.lower()
            or line.endswith(".md")
        ):
            findings.append(
                Finding(
                    rule_id="format",
                    severity=Severity.ERROR,
                    message=line.strip() or "Markdown would be reformatted",
                    fix=FixHint(description="Run mdformat", command="mdformat ."),
                )
            )
    if not findings:
        findings.append(
            Finding(
                rule_id="format",
                severity=Severity.ERROR,
                message=text.splitlines()[-1] if text else "Markdown formatting check failed",
            )
        )
    return findings


def _parse_yamlfmt(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        if line.strip():
            findings.append(
                Finding(
                    rule_id="format",
                    severity=Severity.ERROR,
                    message=line.strip(),
                    fix=FixHint(description="Run yamlfmt", command="yamlfmt ."),
                )
            )
    return findings


def _parse_cli_text(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            findings.append(
                Finding(
                    rule_id="check",
                    severity=Severity.ERROR,
                    message=stripped,
                )
            )
    return findings


def _parse_semgrep(stdout: str) -> list[Finding]:
    if not stdout.strip():
        return []
    payload = json.loads(stdout)
    findings: list[Finding] = []
    for item in payload.get("results", []):
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {})
        findings.append(
            Finding(
                rule_id=item.get("check_id", "semgrep"),
                severity=Severity.ERROR
                if extra.get("severity", "").upper() in {"ERROR", "HIGH"}
                else Severity.WARNING,
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
        )
    return findings


def _parse_deadcode(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(r"(?P<file>[^:]+):(?P<line>\d+):\s*(?P<code>DC\d+):\s*(?P<message>.+)")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            findings.append(
                Finding(
                    rule_id=match.group("code"),
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                    ),
                )
            )
    if not findings and re.search(r"DC\d+", text):
        findings.append(
            Finding(rule_id="deadcode", severity=Severity.ERROR, message=text.strip()[:500])
        )
    return findings


def _parse_vulture(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<confidence>\d+)%\s*confidence:\s*(?P<message>.+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                Finding(
                    rule_id="vulture",
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                    ),
                )
            )
    return findings


def _parse_pydeps_cycles(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text or "No import cycles detected" in text:
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and "No import cycles" not in stripped:
            findings.append(
                Finding(
                    rule_id="import-cycle",
                    severity=Severity.ERROR,
                    message=stripped,
                )
            )
    return findings


def _parse_pytest(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings: list[Finding] = []
    fail_pattern = re.compile(r"^(?P<file>[^\s]+):(?P<line>\d+):\s*(?P<message>.+)$")
    for line in text.splitlines():
        if line.startswith("FAILED ") or " FAILED" in line:
            findings.append(
                Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip())
            )
            continue
        match = fail_pattern.match(line.strip())
        if match and (
            "error" in match.group("message").lower() or "failed" in match.group("message").lower()
        ):
            findings.append(
                Finding(
                    rule_id="pytest",
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(file=match.group("file"), line=int(match.group("line"))),
                )
            )
    if not findings:
        summary = [
            line
            for line in text.splitlines()
            if "failed" in line.lower() or "error" in line.lower()
        ]
        for line in summary[-3:]:
            findings.append(
                Finding(rule_id="pytest", severity=Severity.ERROR, message=line.strip())
            )
    return findings


def _parse_gitleaks(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _parse_cli_text(stdout, stderr)
    findings: list[Finding] = []
    for item in payload:
        findings.append(
            Finding(
                rule_id=item.get("RuleID", "gitleaks"),
                severity=Severity.ERROR,
                message=f"Secret detected: {item.get('Description', 'potential leak')}",
                location=Location(
                    file=item.get("File", ""),
                    line=item.get("StartLine"),
                    end_line=item.get("EndLine"),
                ),
            )
        )
    return findings


def _parse_codespell(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):\s*(?P<wrong>[^=]+)\s*==>\s*(?P<right>[^\s]+)"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            findings.append(
                Finding(
                    rule_id="spelling",
                    severity=Severity.ERROR,
                    message=f"{match.group('wrong').strip()} -> {match.group('right').strip()}",
                    location=Location(file=match.group("file"), line=int(match.group("line"))),
                )
            )
    return findings


def _parse_markdownlint(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _parse_cli_text(stdout, stderr)
    findings: list[Finding] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            file_path = item.get("fileName", item.get("file", ""))
            findings.append(
                Finding(
                    rule_id=item.get("ruleNames", ["markdownlint"])[0]
                    if item.get("ruleNames")
                    else "markdownlint",
                    severity=Severity.ERROR,
                    message=item.get(
                        "ruleDescription", item.get("ruleInformation", "markdownlint finding")
                    ),
                    location=Location(
                        file=file_path,
                        line=item.get("lineNumber"),
                        column=item.get("columnNumber"),
                    ),
                )
            )
        return findings
    if isinstance(payload, dict):
        for file_path, items in payload.items():
            for item in items:
                findings.append(
                    Finding(
                        rule_id=item.get("ruleNames", ["markdownlint"])[0]
                        if item.get("ruleNames")
                        else "markdownlint",
                        severity=Severity.ERROR,
                        message=item.get(
                            "ruleDescription", item.get("ruleInformation", "markdownlint finding")
                        ),
                        location=Location(
                            file=file_path,
                            line=item.get("lineNumber"),
                            column=item.get("columnNumber"),
                        ),
                    )
                )
    return findings


def _parse_yamllint(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*\[(?P<severity>error|warning)\]\s*(?P<message>.+)$"
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match and match.group("severity") == "error":
            findings.append(
                Finding(
                    rule_id="yamllint",
                    severity=Severity.ERROR,
                    message=match.group("message").strip(),
                    location=Location(
                        file=match.group("file"),
                        line=int(match.group("line")),
                        column=int(match.group("col")),
                    ),
                )
            )
    return findings


def _parse_hadolint(stdout: str, stderr: str) -> list[Finding]:
    payload_text = stdout.strip() or stderr.strip()
    if not payload_text:
        return []
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _parse_cli_text(stdout, stderr)
    findings: list[Finding] = []
    for item in payload:
        findings.append(
            Finding(
                rule_id=item.get("code", "hadolint"),
                severity=Severity.ERROR if item.get("level") == "error" else Severity.WARNING,
                message=item.get("message", "hadolint finding"),
                location=Location(file=item.get("file", ""), line=item.get("line")),
            )
        )
    return findings


def _parse_mutmut(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    if "passed" in text.lower() and "failed" not in text.lower():
        return []
    return _parse_cli_text(stdout, stderr)


def _parse_sourcery(stdout: str, stderr: str) -> list[Finding]:
    text = (stdout or stderr).strip()
    if not text:
        return []
    findings: list[Finding] = []
    for line in text.splitlines():
        if line.strip() and not line.lower().startswith("reviewing"):
            findings.append(
                Finding(
                    rule_id="sourcery",
                    severity=Severity.WARNING,
                    message=line.strip(),
                )
            )
    return findings


def _finding_from_dict(item: dict) -> Finding:
    location = None
    loc = item.get("location")
    if isinstance(loc, dict) and loc.get("file"):
        location = Location(
            file=loc.get("file", ""),
            line=loc.get("line"),
            column=loc.get("column"),
            end_line=loc.get("end_line"),
            end_column=loc.get("end_column"),
        )
    severity_raw = str(item.get("severity", "error")).lower()
    severity = Severity.ERROR
    if severity_raw == "warning":
        severity = Severity.WARNING
    elif severity_raw == "info":
        severity = Severity.INFO
    fix = None
    fix_data = item.get("fix")
    if isinstance(fix_data, dict):
        fix = FixHint(
            description=fix_data.get("description"),
            command=fix_data.get("command"),
        )
    return Finding(
        rule_id=item.get("rule_id", "gate"),
        severity=severity,
        message=item.get("message", "script gate finding"),
        location=location,
        snippet=item.get("snippet"),
        fix=fix,
    )


def _parse_gate_json(stdout: str, stderr: str) -> list[Finding]:
    text = stdout.strip()
    if not text:
        return _parse_script_text(stdout, stderr)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _parse_script_text(stdout, stderr)
    if isinstance(payload, dict) and "findings" in payload:
        items = payload["findings"]
    elif isinstance(payload, list):
        items = payload
    else:
        return []
    return [_finding_from_dict(item) for item in items if isinstance(item, dict)]


def _parse_script_text(stdout: str, stderr: str) -> list[Finding]:
    text = stdout or stderr
    findings: list[Finding] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("FAIL "):
            findings.append(
                Finding(
                    rule_id="gate",
                    severity=Severity.ERROR,
                    message=stripped.removeprefix("FAIL ").strip(),
                )
            )
            continue
        if stripped.startswith("FAIL:"):
            findings.append(
                Finding(
                    rule_id="gate",
                    severity=Severity.ERROR,
                    message=stripped.removeprefix("FAIL:").strip(),
                )
            )
            continue
        if re.match(r"^FAIL\b", stripped):
            findings.append(
                Finding(
                    rule_id="gate",
                    severity=Severity.ERROR,
                    message=stripped,
                )
            )
    return findings
