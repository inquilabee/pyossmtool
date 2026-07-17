"""Read nearby source lines for findings that point at a file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shipgate.server.models import FindingRecord

_CONTEXT_RADIUS = 5


@dataclass(frozen=True)
class SourceLine:
    number: int
    text: str
    highlighted: bool


@dataclass(frozen=True)
class FindingSourceContext:
    lines: tuple[SourceLine, ...]


def source_contexts(
    project_root: Path,
    findings: list[FindingRecord],
    *,
    context_lines: int = _CONTEXT_RADIUS,
) -> dict[str, FindingSourceContext]:
    """Map finding id -> ±context_lines around the reported line (files only)."""
    root = project_root.resolve()
    contexts: dict[str, FindingSourceContext] = {}
    for finding in findings:
        if not finding.file or finding.line is None:
            continue
        snippet = _read_snippet(root, finding.file, finding.line, radius=context_lines)
        if snippet is not None:
            contexts[finding.id] = snippet
    return contexts


def message_contexts(findings: list[FindingRecord]) -> dict[str, FindingSourceContext]:
    """Map finding id -> line-numbered message text for multiline output."""
    contexts: dict[str, FindingSourceContext] = {}
    for finding in findings:
        snippet = message_context(finding.message, highlight_line=finding.line)
        if snippet is not None:
            contexts[finding.id] = snippet
    return contexts


def message_context(message: str, *, highlight_line: int | None = None) -> FindingSourceContext | None:
    """Split a multiline message into numbered lines for display."""
    if "\n" not in message:
        return None
    lines = message.splitlines()
    if not lines:
        return None
    return FindingSourceContext(
        lines=tuple(
            SourceLine(number=index, text=text, highlighted=highlight_line == index if highlight_line else False)
            for index, text in enumerate(lines, start=1)
        ),
    )


def _safe_read_lines(root: Path, rel_file: str) -> list[str] | None:
    path = (root / rel_file).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        file_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return file_lines or None


def _read_snippet(
    root: Path,
    rel_file: str,
    line: int,
    *,
    radius: int,
) -> FindingSourceContext | None:
    file_lines = _safe_read_lines(root, rel_file)
    if file_lines is None:
        return None
    index = max(0, min(line - 1, len(file_lines) - 1))
    start = max(0, index - radius)
    end = min(len(file_lines), index + radius + 1)
    return FindingSourceContext(
        lines=tuple(
            SourceLine(number=lineno, text=file_lines[lineno - 1], highlighted=lineno == line)
            for lineno in range(start + 1, end + 1)
        ),
    )
