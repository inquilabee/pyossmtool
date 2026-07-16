"""Documented-acronym policy gate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pyaitools.ignore import EffectiveIgnores, ignores_from_env

ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
FENCED_CODE_BLOCK_RE = re.compile(r"(`{3,})[\s\S]*?\1", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")

BUILTIN_EXEMPT: frozenset[str] = frozenset(
    {
        "AA",
        "AGENTS",
        "AMC",
        "AND",
        "API",
        "ASGI",
        "AST",
        "AVOIDANCE",
        "BIGCO",
        "BLUE",
        "BMO",
        "BUMPY",
        "CALM",
        "CHEAP",
        "CI",
        "CLI",
        "CM",
        "CORS",
        "CPU",
        "CRUD",
        "CSRF",
        "CSS",
        "CSV",
        "DD",
        "DEAR",
        "DELETE",
        "DO",
        "DTO",
        "DX",
        "ECHO",
        "EPSILON",
        "ESG",
        "FAIL",
        "FAILED",
        "FIFO",
        "FLAT",
        "FK",
        "GB",
        "GET",
        "GICS",
        "GPL",
        "GREEN",
        "HEAD",
        "HEREDOC",
        "HIGH",
        "HOW",
        "HTML",
        "HTTP",
        "HTTPS",
        "IA",
        "IDE",
        "ID",
        "II",
        "III",
        "INFY",
        "IO",
        "IP",
        "IPO",
        "ISO",
        "IST",
        "IT",
        "JSON",
        "JSONB",
        "JSCPD",
        "JWT",
        "KNOWLEDGE",
        "LOC",
        "LOW",
        "MA",
        "MB",
        "MEDIUM",
        "MID",
        "MINT",
        "MM",
        "MOTHERSON",
        "MOTHERSUMI",
        "NO",
        "NOT",
        "NOVA",
        "NULL",
        "OK",
        "ON",
        "OOM",
        "OPAL",
        "OPTIONS",
        "PARTIAL",
        "PASS",
        "PATCH",
        "PATH",
        "PDF",
        "PEM",
        "PG",
        "PINE",
        "PK",
        "POST",
        "PUT",
        "QUILL",
        "RAM",
        "README",
        "RED",
        "RELIANCE",
        "REST",
        "ROSE",
        "RUN",
        "SCOPE",
        "SHA",
        "SIGINT",
        "SIGTERM",
        "SKILL",
        "SLO",
        "SMALLB",
        "SMOOTH",
        "SPA",
        "SQL",
        "SSG",
        "SSR",
        "SSH",
        "SVG",
        "SURVIVAL",
        "TBD",
        "TEMPORAL",
        "TEXT",
        "TIMESTAMPTZ",
        "TODO",
        "TS",
        "UPDATE",
        "UP",
        "URL",
        "UTC",
        "UUID",
        "VM",
        "VPN",
        "WCAG",
        "WHAT",
        "WILD",
        "WORKDIR",
        "WSL",
        "XML",
        "YAML",
        "YYYY",
        "ZIP",
    }
)


@dataclass(frozen=True, slots=True)
class AcronymViolation:
    path: str
    line: int
    token: str


def strip_markdown_code(text: str) -> str:
    without_fences = FENCED_CODE_BLOCK_RE.sub("", text)
    return INLINE_CODE_RE.sub("", without_fences)


def load_allowlist(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"acronym allowlist must be a YAML mapping: {path}"
        raise ValueError(msg)
    return {str(key) for key in raw}


def find_violations_in_line(line: str, *, allowlisted: set[str]) -> list[str]:
    tokens: list[str] = []
    for match in ACRONYM_RE.finditer(line):
        token = match.group(0)
        if token in BUILTIN_EXEMPT or token in allowlisted:
            continue
        tokens.append(token)
    return tokens


def find_violations_in_text(
    text: str, *, path: str, allowlisted: set[str]
) -> list[AcronymViolation]:
    prose = strip_markdown_code(text)
    violations: list[AcronymViolation] = []
    for line_no, line in enumerate(prose.splitlines(), start=1):
        for token in find_violations_in_line(line, allowlisted=allowlisted):
            violations.append(AcronymViolation(path=path, line=line_no, token=token))
    return violations


def iter_markdown_files(scan_roots: tuple[str, ...], repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in scan_roots:
        candidate = repo_root / root
        if candidate.is_file():
            files.append(candidate)
            continue
        if candidate.is_dir():
            files.extend(sorted(candidate.rglob("*.md")))
    return files


def scan_paths(
    *,
    repo_root: Path,
    allowlist_path: Path,
    scan_roots: tuple[str, ...],
    ignores: EffectiveIgnores | None = None,
) -> list[AcronymViolation]:
    allowlisted = load_allowlist(allowlist_path)
    violations: list[AcronymViolation] = []
    for file_path in iter_markdown_files(scan_roots, repo_root):
        rel = file_path.relative_to(repo_root).as_posix()
        if ignores and ignores.is_ignored(rel):
            continue
        text = file_path.read_text(encoding="utf-8")
        violations.extend(find_violations_in_text(text, path=rel, allowlisted=allowlisted))
    return violations


def findings_from_violations(violations: list[AcronymViolation]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in violations:
        findings.append(
            {
                "rule_id": "undocumented-acronym",
                "severity": "error",
                "message": f"undocumented acronym {item.token!r}",
                "location": {"file": item.path, "line": item.line},
            }
        )
    return findings


def settings_from_config(config: dict[str, Any]) -> tuple[tuple[str, ...], Path | None]:
    scan_roots = tuple(str(item) for item in config.get("scan_roots", ["docs/", "AGENTS.md"]))
    allowlist_file = config.get("allowlist_file")
    allowlist_path = Path(str(allowlist_file)) if allowlist_file else None
    return scan_roots, allowlist_path


def run_gate(
    *,
    root: Path,
    config: dict[str, Any],
    report_path: Path | None,
) -> int:
    scan_roots, allowlist_path = settings_from_config(config)
    allowlist_path = _require_allowlist_path(root, allowlist_path)
    violations = scan_paths(
        repo_root=root,
        allowlist_path=allowlist_path,
        scan_roots=scan_roots,
        ignores=ignores_from_env(root),
    )
    _write_acronym_report(violations, report_path)
    return _acronym_exit(violations)


def _require_allowlist_path(root: Path, allowlist_path: Path | None) -> Path:
    if allowlist_path is None:
        msg = "acronym allowlist_file is required in gate config"
        raise ValueError(msg)
    if not allowlist_path.is_absolute():
        return root / allowlist_path
    return allowlist_path


def _write_acronym_report(violations, report_path: Path | None) -> None:
    if not report_path:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"findings": findings_from_violations(violations)}
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _acronym_exit(violations) -> int:
    if not violations:
        return 0
    for item in violations:
        print(
            f"FAIL acronym: {item.path}:{item.line}: undocumented acronym {item.token!r}",
            file=sys.stderr,
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Documented-acronym gate.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        msg = f"Gate config must be a mapping: {args.config}"
        raise ValueError(msg)
    return run_gate(root=root, config=config, report_path=args.report)


if __name__ == "__main__":
    raise SystemExit(main())
