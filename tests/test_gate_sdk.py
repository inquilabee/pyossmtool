"""Tests for gate_sdk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shipgate.gate_sdk import Gate


def test_gate_writes_structured_findings(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SHIPGATE_REPORT", str(report))
    monkeypatch.setenv("SHIPGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPGATE_TARGET", ".")

    gate = Gate("demo")
    gate.fail("rule-a", "problem", file="src/a.py", line=3)
    with pytest.raises(SystemExit) as exc:
        gate.finish()
    assert exc.value.code == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["rule_id"] == "rule-a"


def test_gate_finish_passes_when_clean(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SHIPGATE_REPORT", str(report))
    with pytest.raises(SystemExit) as exc:
        Gate("demo").finish()
    assert exc.value.code == 0
