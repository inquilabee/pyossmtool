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
