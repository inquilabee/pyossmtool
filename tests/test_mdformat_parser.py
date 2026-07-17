"""Tests for mdformat / yamlfmt text parsers."""

from __future__ import annotations

from shipgate.parsers.format_text import MdformatParser


def test_mdformat_parses_multiline_error_with_file_path() -> None:
    stderr = """Error: File
"/home/dayhatt/workspace/pyaitools/.shipgate/worktrees/main-0d6e4079e367/CONTRIBUTING.md"
is not formatted.
"""
    findings = MdformatParser().parse("", stderr)
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.file.endswith("CONTRIBUTING.md")
    assert findings[0].message == "CONTRIBUTING.md is not formatted"


def test_mdformat_empty_output_yields_nothing() -> None:
    assert MdformatParser().parse("", "") == []
