"""Expand check include globs and format tool argv target slots."""

from __future__ import annotations

import re
from pathlib import Path

from pyossmtool.models import CheckDef, ProjectConfig, SuiteCheckRef, SuiteDef

_BRACE_PATTERN = re.compile(r"\{([^{}]+)\}")


def resolve_suite_target(
    check_ref: SuiteCheckRef,
    suite: SuiteDef,
    project_config: ProjectConfig | None,
) -> str:
    if check_ref.target:
        return check_ref.target
    if project_config is not None and suite.id == project_config.suite:
        return project_config.target
    return suite.target or "."


def expand_include_globs(root: Path, patterns: list[str]) -> list[str]:
    """Return sorted relative paths matching include patterns under root."""
    if not patterns:
        return []
    root = root.resolve()
    if not root.exists():
        return []
    matches: set[str] = set()
    for pattern in patterns:
        for expanded in _expand_braces(pattern):
            matches.update(_glob_pattern(root, expanded))
    return sorted(matches)


def _expand_braces(pattern: str) -> list[str]:
    match = _BRACE_PATTERN.search(pattern)
    if not match:
        return [pattern]
    options = match.group(1).split(",")
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]
    results: list[str] = []
    for option in options:
        results.extend(_expand_braces(f"{prefix}{option.strip()}{suffix}"))
    return results


def _glob_pattern(root: Path, pattern: str) -> set[str]:
    found: set[str] = set()
    for path in root.glob(pattern):
        if not path.is_file():
            continue
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            continue
        found.add(str(rel).replace("\\", "/"))
    return found


def format_check_argv(check_argv: list[str], argv_targets: list[str], format_values: dict[str, str]) -> list[str]:
    formatted: list[str] = []
    for part in check_argv:
        if part == "{target}":
            formatted.extend(argv_targets)
            continue
        if "{target}" in part:
            for target in argv_targets:
                formatted.append(part.format(target=target, **format_values))
            continue
        formatted.append(part.format(**format_values))
    return formatted


def compose_tool_argv(
    binary: str,
    tool_id: str,
    config_argv: list[str],
    ignore_argv: list[str],
    formatted: list[str],
    post_subcommand: bool,
) -> list[str]:
    if post_subcommand and formatted:
        return [binary, formatted[0], *config_argv, *ignore_argv, *formatted[1:]]
    if tool_id == "pytest" and ignore_argv:
        return [binary, *ignore_argv, *formatted]
    return [binary, *config_argv, *ignore_argv, *formatted]


def build_tool_argv(
    *,
    binary: str,
    tool_id: str,
    config_argv: list[str],
    ignore_argv: list[str],
    check_argv: list[str],
    argv_targets: list[str],
    format_values: dict[str, str],
    post_subcommand: bool = False,
) -> list[str]:
    formatted = format_check_argv(check_argv, argv_targets, format_values)
    return compose_tool_argv(binary, tool_id, config_argv, ignore_argv, formatted, post_subcommand)


def coverage_target(check: CheckDef) -> str:
    if check.policy and check.policy.coverage_source:
        return check.policy.coverage_source
    return "src/"
