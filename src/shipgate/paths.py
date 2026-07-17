"""Canonical repo-relative paths for findings and ignores."""

from __future__ import annotations

from pathlib import Path


def normalize_finding_path(path: str | None, *, project_root: Path | None = None) -> str | None:
    """Return a repo-relative POSIX path, or None if empty.

    Strips leading ``./``, normalizes separators, and when ``project_root`` is set
    converts absolute paths under that root into relative form.
    """
    normalized = _normalize_separators(path)
    if not normalized:
        return None
    if project_root is not None and Path(normalized).is_absolute():
        normalized = _relativize(normalized, project_root)
    return normalized or None


def _normalize_separators(path: str | None) -> str | None:
    if path is None:
        return None
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _relativize(normalized: str, project_root: Path) -> str:
    try:
        return Path(normalized).resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        # Outside project root — keep absolute POSIX form without ./
        return Path(normalized).as_posix()
