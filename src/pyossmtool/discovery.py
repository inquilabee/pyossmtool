"""Discover check targets from tool file globs under a scan root.

Empty ``ToolDef.files`` (and no check-level ``include``) means the tool accepts a
directory root — pass ``target`` through unchanged. Non-empty globs expand to
matching files under ``project_root / target``, filtered by the effective
gitignore matcher. An empty match set means the check should be skipped
(silent pass).
"""

from __future__ import annotations

from pathlib import Path

from pyossmtool.ignore import EffectiveIgnores
from pyossmtool.models import CheckDef, ToolDef
from pyossmtool.target_expand import expand_include_globs


def effective_file_globs(check: CheckDef, tool: ToolDef) -> list[str]:
    """Check-level include narrows; otherwise use tool files."""
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
) -> list[str] | None:
    globs = effective_file_globs(check, tool)
    if not globs:
        return [target]
    root = (project_root / target).resolve()
    matches = expand_include_globs(root, globs)
    if ignores is not None:
        matches = [rel for rel in matches if not _is_ignored(target, rel, ignores)]
    if not matches:
        return None
    return [str(Path(target) / rel) for rel in matches]


def _is_ignored(target: str, rel: str, ignores: EffectiveIgnores) -> bool:
    repo_relative = str(Path(target) / rel).replace("\\", "/")
    if repo_relative.startswith("./"):
        repo_relative = repo_relative[2:]
    return ignores.is_ignored(repo_relative)
