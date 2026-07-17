"""Tests for ruff format check output parsing."""

from __future__ import annotations

from shipgate.parsers.ruff import RuffFormatParser


def test_ruff_format_parser_parses_would_reformat_colon_path() -> None:
    stdout = "Would reformat: src/foo.py\nWould reformat: src/bar.py\n"
    findings = RuffFormatParser().parse(stdout)
    assert len(findings) == 2
    assert findings[0].location is not None
    assert findings[0].location.file == "src/foo.py"
    assert findings[1].location is not None
    assert findings[1].location.file == "src/bar.py"
    assert findings[0].location.file != "Would"
