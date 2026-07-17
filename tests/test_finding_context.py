"""Tests for finding source-context snippets."""

from __future__ import annotations

from pathlib import Path

from shipgate.server.finding_context import message_context, message_contexts, source_contexts
from shipgate.server.models import FindingCategory, FindingRecord


def _finding(*, fid: str, file: str, line: int | None) -> FindingRecord:
    return FindingRecord(
        id=fid,
        run_id="run1",
        check_id="ruff.lint",
        tool_id="ruff",
        rule_id="E501",
        severity="error",
        message="too long",
        file=file,
        line=line,
        category=FindingCategory.CODE,
    )


def test_source_contexts_include_highlighted_line(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    path = src / "app.py"
    lines = [f"line {index}\n" for index in range(1, 21)]
    path.write_text("".join(lines), encoding="utf-8")

    contexts = source_contexts(
        tmp_path,
        [_finding(fid="f1", file="src/app.py", line=10)],
        context_lines=5,
    )
    assert "f1" in contexts
    snippet = contexts["f1"]
    assert len(snippet.lines) == 11
    highlighted = [line for line in snippet.lines if line.highlighted]
    assert len(highlighted) == 1
    assert highlighted[0].number == 10
    assert highlighted[0].text == "line 10"


def test_source_contexts_skip_missing_files(tmp_path: Path) -> None:
    contexts = source_contexts(
        tmp_path,
        [_finding(fid="f1", file="missing.py", line=1)],
    )
    assert contexts == {}


def test_source_contexts_skip_findings_without_line(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    contexts = source_contexts(
        tmp_path,
        [_finding(fid="f1", file="a.py", line=None)],
    )
    assert contexts == {}


def test_message_context_splits_multiline_output() -> None:
    snippet = message_context("FAILED tests/test_cli.py\nAssertionError: boom\n1 failed")
    assert snippet is not None
    assert len(snippet.lines) == 3
    assert snippet.lines[0].number == 1
    assert snippet.lines[0].text == "FAILED tests/test_cli.py"


def test_message_contexts_skip_single_line_messages() -> None:
    finding = FindingRecord(
        id="f1",
        run_id="run1",
        check_id="mutmut.run",
        tool_id="mutmut",
        rule_id="mutmut",
        severity="error",
        message="runner returned 1",
        category=FindingCategory.TOOL,
    )
    assert message_contexts([finding]) == {}
