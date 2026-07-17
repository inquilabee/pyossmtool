"""Parser coverage for format and shell tools."""

from __future__ import annotations

from shipgate.parsers.format_text import MdformatParser, YamlfmtParser
from shipgate.parsers.shell import ShellcheckParser, ShfmtDiffParser


def test_mdformat_parser_error_file_block() -> None:
    text = 'Error: File "docs/readme.md" is not formatted.'
    findings = MdformatParser().parse(text, "")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.file == "docs/readme.md"
    assert findings[0].fix is not None


def test_mdformat_parser_line_and_fallback_paths() -> None:
    line_findings = MdformatParser().parse('Would be reformatted: "notes.md"\n', "")
    assert line_findings[0].rule_id == "format"
    fallback = MdformatParser().parse("unexpected mdformat output", "")
    assert fallback[0].message == "unexpected mdformat output"


def test_yamlfmt_parser_emits_line_findings() -> None:
    findings = YamlfmtParser().parse("foo.yaml: formatting needed\n", "")
    assert len(findings) == 1
    assert findings[0].fix is not None
    assert findings[0].fix.command == "yamlfmt ."


def test_shfmt_diff_parser_maps_file_hunks() -> None:
    diff = """--- script.sh
+++ script.sh
@@ -1 +1 @@
-echo hi
+echo hello
"""
    findings = ShfmtDiffParser().parse(diff, "")
    assert len(findings) >= 2
    assert findings[0].location is not None
    assert findings[0].location.file == "script.sh"


def test_shfmt_diff_parser_fallback_when_no_hunks() -> None:
    findings = ShfmtDiffParser().parse("non-diff noise", "")
    assert findings[0].message == "Shell formatting differences detected"


def test_shellcheck_parser_maps_info_level() -> None:
    parser = ShellcheckParser()
    finding = parser.map_item({"code": 1, "level": "info", "message": "note", "file": "a.sh", "line": 2})  # ty: ignore[unresolved-attribute]
    assert finding.severity.value == "info"
