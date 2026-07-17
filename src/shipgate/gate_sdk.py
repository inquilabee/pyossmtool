"""Python SDK for user-authored script gates."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import NoReturn


class Gate:
    """Structured findings writer for Python gate scripts."""

    def __init__(self, name: str = "script-gate") -> None:
        self.name = name
        self._report_path = os.environ.get("SHIPGATE_REPORT")
        self.root = os.environ.get("SHIPGATE_ROOT", ".")
        self.target = os.environ.get("SHIPGATE_TARGET", ".")
        self.check_id = os.environ.get("SHIPGATE_CHECK_ID", "")
        self.gate_config = os.environ.get("SHIPGATE_GATE_CONFIG", "")
        self._finding_count = 0
        if not self._report_path:
            print("Gate: SHIPGATE_REPORT is not set (shipgate runner should set this)", file=sys.stderr)
            raise SystemExit(2)
        path = Path(self._report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"findings": []}\n', encoding="utf-8")

    def fail(
        self,
        rule_id: str,
        message: str,
        *,
        file: str | None = None,
        line: int | None = None,
        severity: str = "error",
    ) -> None:
        self._append(rule_id, severity, message, file=file, line=line)
        print(f"FAIL {rule_id}: {message}", file=sys.stderr)

    def warn(self, rule_id: str, message: str, *, file: str | None = None, line: int | None = None) -> None:
        self._append(rule_id, "warning", message, file=file, line=line)
        print(f"WARN {rule_id}: {message}", file=sys.stderr)

    def _append(
        self,
        rule_id: str,
        severity: str,
        message: str,
        *,
        file: str | None,
        line: int | None,
    ) -> None:
        assert self._report_path is not None
        payload = json.loads(Path(self._report_path).read_text(encoding="utf-8"))
        finding: dict[str, object] = {
            "rule_id": rule_id,
            "severity": severity,
            "message": message,
        }
        if file:
            location: dict[str, object] = {"file": file}
            if line is not None:
                location["line"] = line
            finding["location"] = location
        payload.setdefault("findings", []).append(finding)
        Path(self._report_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._finding_count += 1

    def finish(self) -> NoReturn:
        if self._finding_count > 0:
            print(f"gate '{self.name}' failed with {self._finding_count} finding(s)", file=sys.stderr)
            raise SystemExit(1)
        raise SystemExit(0)
