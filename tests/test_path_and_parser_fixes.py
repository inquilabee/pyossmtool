"""Tests for path normalization and deadcode/jscpd/bandit parsers."""

from __future__ import annotations

import json
from pathlib import Path

from shipgate.models import CheckDef, CheckMode, CheckPolicy, Severity
from shipgate.parsers.analysis import BanditParser, DeadcodeParser, JscpdParser, PytestParser
from shipgate.paths import normalize_finding_path


def test_normalize_finding_path_strips_dot_slash_and_empty() -> None:
    assert normalize_finding_path("./src/foo.py") == "src/foo.py"
    assert normalize_finding_path("src\\foo.py") == "src/foo.py"
    assert normalize_finding_path("") is None
    assert normalize_finding_path(None) is None


def test_normalize_finding_path_absolutizes_under_root(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    absolute = root / "src" / "a.py"
    assert normalize_finding_path(str(absolute), project_root=root) == "src/a.py"


def test_deadcode_parses_v2_line_with_column() -> None:
    stdout = "src/shipgate/error_formatters.py:13:0: DC01 Variable `BUILTIN_FORMATS` is never used\n"
    findings = DeadcodeParser().parse(stdout)
    assert len(findings) == 1
    assert findings[0].rule_id == "DC01"
    assert findings[0].location is not None
    assert findings[0].location.file == "src/shipgate/error_formatters.py"
    assert findings[0].location.line == 13
    assert findings[0].location.column == 0
    assert "BUILTIN_FORMATS" in findings[0].message


def test_bandit_strips_dot_slash_filename() -> None:
    payload = {
        "results": [
            {
                "test_id": "B101",
                "issue_severity": "LOW",
                "issue_text": "assert used",
                "filename": "./tests/test_cli.py",
                "line_number": 10,
            }
        ]
    }
    findings = BanditParser().parse(json.dumps(payload))
    assert findings[0].location is not None
    assert findings[0].location.file == "tests/test_cli.py"


def test_jscpd_threshold_emits_summary_and_duplicates() -> None:
    check = CheckDef(
        id="jscpd.duplication",
        tool="jscpd",
        name="jscpd",
        description="duplication",
        parser="jscpd_json",
        mode=CheckMode.CHECK,
        policy=CheckPolicy(max_duplication_percent=50),
    )
    payload = {
        "statistics": {"total": {"percentage": 80.2}},
        "duplicates": [
            {
                "lines": 12,
                "format": "python",
                "firstFile": {"name": "./src/a.py", "startLoc": {"line": 4}},
                "secondFile": {"name": "./src/b.py"},
            }
        ],
    }
    findings = JscpdParser().parse_payload(payload, check)  # ty: ignore[unresolved-attribute]
    assert findings[0].rule_id == "duplication"
    assert findings[0].location is None
    assert findings[1].rule_id == "duplicate-block"
    assert findings[1].location is not None
    assert findings[1].location.file == "src/a.py"
    assert findings[1].severity == Severity.WARNING


def test_pytest_parser_ignores_coverage_rows_with_error_in_filename() -> None:
    stdout = (
        "src/shipgate/error_formatters.py            143      2    99%   21, 209\n"
        "TOTAL                                        3160    626    80%\n"
    )
    assert PytestParser().parse(stdout) == []
