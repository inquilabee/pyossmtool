# tests/test_parser_registry.py
from __future__ import annotations

import json

from pyaitools.models import Finding, Severity
from pyaitools.parsers.base import REGISTRY, Parser, register
from pyaitools.parsers.patterns import JsonListParser


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

        def parse_one(self, item: dict) -> Finding:
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
    from pyaitools.parsers import shell  # noqa: F401
    from pyaitools.parsers.base import REGISTRY

    payload = json.dumps(
        [{"code": 2086, "level": "warning", "message": "Double quote", "file": "a.sh", "line": 1}]
    )
    findings = REGISTRY["shellcheck_json"]().parse(payload, "")
    assert findings[0].rule_id == "SC2086"
    assert findings[0].location is not None
    assert findings[0].location.file == "a.sh"


def test_ruff_and_bandit_json_registered() -> None:
    from pyaitools.parsers import analysis, ruff  # noqa: F401
    from pyaitools.parsers.base import REGISTRY

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
