"""Folder breadth policy gate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyaitools.ignore import EffectiveIgnores, ignores_from_env


@dataclass(frozen=True, slots=True)
class DirBreadthViolation:
    path: str
    count: int
    max_allowed: int


@dataclass(frozen=True, slots=True)
class FolderBreadthReport:
    max_allowed: int
    scan_roots: tuple[str, ...]
    extensions: tuple[str, ...]
    leaf_dirs_scanned: int
    leaf_dirs_over_max: int
    worst_leaf_dir: str
    worst_leaf_count: int
    violations: tuple[DirBreadthViolation, ...]

    def report_metadata(self) -> dict[str, int | str]:
        return {
            "leaf_dirs_scanned": self.leaf_dirs_scanned,
            "worst_leaf_dir": self.worst_leaf_dir,
            "worst_leaf_count": self.worst_leaf_count,
        }


SKIP_DIR_NAMES = frozenset({"__pycache__"})


def load_allowlist(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            entries.add(stripped.rstrip("/"))
    return entries


def settings_from_config(
    config: dict[str, Any],
) -> tuple[int, tuple[str, ...], tuple[str, ...], bool]:
    max_allowed = int(config.get("max_allowed", 12))
    scan_roots = tuple(str(item) for item in config.get("scan_roots", ["src/"]))
    extensions_raw = config.get("extensions", [".py", ".md", ".yaml", ".sh"])
    extensions: list[str] = []
    for part in extensions_raw:
        stripped = str(part).strip()
        if not stripped:
            continue
        extensions.append(stripped if stripped.startswith(".") else f".{stripped}")
    strict = bool(config.get("strict", True))
    return max_allowed, scan_roots, tuple(extensions), strict


def iter_scan_directories(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    directories = [base]
    for path in sorted(base.rglob("*")):
        if path.is_dir() and path.name not in SKIP_DIR_NAMES:
            directories.append(path)
    return directories


def count_direct_files(directory: Path, extensions: tuple[str, ...]) -> int:
    count = 0
    for child in directory.iterdir():
        if not child.is_file():
            continue
        if child.name == "__init__.py":
            continue
        if child.suffix in extensions:
            count += 1
    return count


def is_allowlisted(rel_posix: str, allowlist: set[str]) -> bool:
    normalized = rel_posix.rstrip("/")
    if normalized in allowlist:
        return True
    return any(normalized.startswith(f"{entry}/") for entry in allowlist)


def scan_folder_breadth(
    root: Path,
    *,
    max_allowed: int,
    scan_roots: tuple[str, ...],
    extensions: tuple[str, ...],
    allowlist: set[str],
    ignores: EffectiveIgnores | None = None,
) -> FolderBreadthReport:
    violations: list[DirBreadthViolation] = []
    dirs_scanned = 0
    worst_path = ""
    worst_count = 0

    for scan_root in scan_roots:
        base = root / scan_root
        for directory in iter_scan_directories(base):
            rel = directory.relative_to(root).as_posix()
            if is_allowlisted(rel, allowlist):
                continue
            if ignores and ignores.is_ignored(rel):
                continue
            file_count = count_direct_files(directory, extensions)
            if file_count == 0:
                continue
            dirs_scanned += 1
            if file_count > worst_count:
                worst_count = file_count
                worst_path = rel
            if file_count > max_allowed:
                violations.append(
                    DirBreadthViolation(path=rel, count=file_count, max_allowed=max_allowed)
                )

    violations.sort(key=lambda item: (-item.count, item.path))
    return FolderBreadthReport(
        max_allowed=max_allowed,
        scan_roots=scan_roots,
        extensions=extensions,
        leaf_dirs_scanned=dirs_scanned,
        leaf_dirs_over_max=len(violations),
        worst_leaf_dir=worst_path,
        worst_leaf_count=worst_count,
        violations=tuple(violations),
    )


def findings_from_report(report: FolderBreadthReport) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for violation in report.violations:
        findings.append(
            {
                "rule_id": "folder-breadth",
                "severity": "error",
                "message": (
                    f"{violation.path} has {violation.count} sibling files "
                    f"(max {violation.max_allowed})"
                ),
                "location": {"file": violation.path},
            }
        )
    return findings


def run_gate(
    *,
    root: Path,
    config: dict[str, Any],
    allowlist_path: Path | None,
    report_path: Path | None,
    strict: bool | None = None,
) -> int:
    max_allowed, scan_roots, extensions, config_strict = settings_from_config(config)
    enforcing = config_strict if strict is None else strict
    allowlist = load_allowlist(allowlist_path or Path())
    report = scan_folder_breadth(
        root,
        max_allowed=max_allowed,
        scan_roots=scan_roots,
        extensions=extensions,
        allowlist=allowlist,
        ignores=ignores_from_env(root),
    )

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"findings": findings_from_report(report), **report.report_metadata()}
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if enforcing and report.leaf_dirs_over_max > 0:
        for violation in report.violations:
            print(
                f"FAIL folder-breadth: {violation.path} has {violation.count} files "
                f"(max {violation.max_allowed})",
                file=sys.stderr,
            )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Folder breadth gate.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", default=None)
    parser.add_argument("--advisory", action="store_true", default=False)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    import yaml

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        msg = f"Gate config must be a mapping: {args.config}"
        raise ValueError(msg)

    allowlist_file = config.get("allowlist_file")
    allowlist_path = None
    if allowlist_file:
        allowlist_path = Path(str(allowlist_file))
        if not allowlist_path.is_absolute():
            allowlist_path = root / allowlist_path

    strict = False if args.advisory else args.strict
    return run_gate(
        root=root,
        config=config,
        allowlist_path=allowlist_path,
        report_path=args.report,
        strict=strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
