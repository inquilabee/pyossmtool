"""Discover check targets from tool file globs under a scan root.

Empty ``ToolDef.files`` (and no check-level ``include``) means the tool accepts a
directory root — pass ``target`` through unchanged. Non-empty globs expand to
matching files under ``project_root / target``, filtered by the effective
gitignore matcher. An empty match set means the check should be skipped
(silent pass).
"""

from __future__ import annotations

from pathlib import Path

from shipgate.ignore import EffectiveIgnores
from shipgate.models import CheckDef, ToolDef
from shipgate.target_expand import expand_include_globs


def effective_file_globs(
    check: CheckDef,
    tool: ToolDef,
    *,
    include_override: list[str] | None = None,
) -> list[str]:
    """Check-level include narrows; CLI override wins when set."""
    if include_override:
        return list(include_override)
    if check.include:
        return list(check.include)
    return list(tool.files)


def argv_targets_for_check(
    *,
    project_root: Path,
    check: CheckDef,
    tool: ToolDef,
    target: str,
    ignores: EffectiveIgnores | None = None,
    include_override: list[str] | None = None,
) -> list[str] | None:
    globs = effective_file_globs(check, tool, include_override=include_override)
    if not globs:
        return [target]
    root = (project_root / target).resolve()
    matches = _filter_ignored(expand_include_globs(root, globs), target, ignores)
    if not matches:
        return None
    return [str(Path(target) / rel) for rel in matches]


def _filter_ignored(matches: list[str], target: str, ignores: EffectiveIgnores | None) -> list[str]:
    if ignores is None:
        return matches
    return [rel for rel in matches if not _is_ignored(target, rel, ignores)]


def _is_ignored(target: str, rel: str, ignores: EffectiveIgnores) -> bool:
    repo_relative = str(Path(target) / rel).replace("\\", "/")
    if repo_relative.startswith("./"):
        repo_relative = repo_relative[2:]
    return ignores.is_ignored(repo_relative)
