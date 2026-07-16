# tests/test_parser_registry.py
from __future__ import annotations

import json

from pyossmtool.models import CheckDef, Finding, Severity, SuccessCriteria
from pyossmtool.parsers import parse_output
from pyossmtool.parsers.base import REGISTRY, Parser, register
from pyossmtool.parsers.patterns import JsonListParser

REQUIRED_PARSER_IDS = {
    "ruff_json",
    "ruff_format_text",
    "ty_concise",
    "shellcheck_json",
    "bandit_json",
    "radon_cc_json",
    "radon_mi_json",
    "jscpd_json",
    "shfmt_diff",
    "mdformat_text",
    "yamlfmt_text",
    "semgrep_json",
    "deadcode_text",
    "vulture_text",
    "pydeps_cycles_text",
    "pytest_text",
    "gitleaks_json",
    "codespell_text",
    "markdownlint_json",
    "yamllint_text",
    "hadolint_json",
    "mutmut_text",
    "sourcery_text",
    "cli_text",
    "gate_json",
    "script_text",
    "noop",
}


def test_register_adds_parser_id() -> None:
    @register
    class _DemoParser(Parser):
        id = "_demo_only"

        def parse(self, stdout: str, stderr: str = "", *, check=None) -> list[Finding]:
            return []

    assert "_demo_only" in REGISTRY
    assert REGISTRY["_demo_only"] is _DemoParser
    REGISTRY.pop("_demo_only", None)


def test_json_list_parser_maps_items() -> None:
    class _Items(JsonListParser):
        id = "_json_demo"

        def map_item(self, item: dict) -> Finding:
            return Finding(
                rule_id=item["id"],
                severity=Severity.ERROR,
                message=item["msg"],
            )

    findings = _Items().parse(json.dumps([{"id": "X", "msg": "hello"}]), "")
    assert len(findings) == 1
    assert findings[0].rule_id == "X"
    assert findings[0].message == "hello"


def test_shellcheck_parser_registered_and_parses() -> None:
    payload = json.dumps([{"code": 2086, "level": "warning", "message": "Double quote", "file": "a.sh", "line": 1}])
    findings = REGISTRY["shellcheck_json"]().parse(payload, "")
    assert findings[0].rule_id == "SC2086"
    assert findings[0].location is not None
    assert findings[0].location.file == "a.sh"


def test_ruff_and_bandit_json_registered() -> None:
    assert "ruff_json" in REGISTRY
    assert "bandit_json" in REGISTRY
    assert REGISTRY["ruff_json"]().parse("[]", "") == []
    bandit_payload = json.dumps(
        {
            "results": [
                {
                    "test_id": "B101",
                    "issue_severity": "HIGH",
                    "issue_text": "assert used",
                    "filename": "a.py",
                    "line_number": 3,
                }
            ]
        }
    )
    findings = REGISTRY["bandit_json"]().parse(bandit_payload, "")
    assert findings[0].rule_id == "B101"


def test_ty_parser_parses_concise_line() -> None:
    line = "src/a.py:1:2: error: Unknown name\n"
    findings = REGISTRY["ty_concise"]().parse(line, "")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.file == "src/a.py"


def test_all_catalog_parser_ids_registered() -> None:
    missing = REQUIRED_PARSER_IDS - set(REGISTRY)
    assert not missing, f"Missing parsers: {sorted(missing)}"


def test_parse_output_ruff_json() -> None:
    check = CheckDef(
        id="ruff.lint",
        tool="ruff",
        name="Ruff",
        description="x",
        parser="ruff_json",
        success=SuccessCriteria(),
    )
    findings = parse_output(check, "[]", "")
    assert findings == []
