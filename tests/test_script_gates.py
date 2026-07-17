from __future__ import annotations

import json
from pathlib import Path

# Ensure registration
import shipgate.parsers  # noqa: F401
from shipgate.models import Severity
from shipgate.parsers.base import REGISTRY
from shipgate.registry import Registry


def test_registry_loads_project_script_gate(tmp_path: Path) -> None:
    catalog = tmp_path / ".shipgate" / "catalog" / "checks"
    catalog.mkdir(parents=True)
    (catalog / "gate.example.yaml").write_text(
        """
id: gate.example
tool: script
name: Example
description: test gate
script: .shipgate/gates/example.sh
parser: gate_json
""".strip()
        + "\n",
        encoding="utf-8",
    )
    registry = Registry(project_root=tmp_path)
    check = registry.get_check("gate.example")
    assert check.tool == "script"
    assert check.script == ".shipgate/gates/example.sh"


def test_parse_gate_json_findings() -> None:
    payload = {
        "findings": [
            {
                "rule_id": "line-limit",
                "severity": "error",
                "message": "too long",
                "location": {"file": "src/a.py", "line": 1},
            }
        ]
    }
    findings = REGISTRY["gate_json"]().parse(json.dumps(payload), "")
    assert len(findings) == 1
    assert findings[0].rule_id == "line-limit"
    assert findings[0].severity == Severity.ERROR
    assert findings[0].location is not None
    assert findings[0].location.file == "src/a.py"


def test_parse_script_text_fail_lines() -> None:
    findings = REGISTRY["script_text"]().parse("", "FAIL module-size: src/foo.py has 999 lines\n")
    assert len(findings) == 1
    assert "foo.py" in findings[0].message
