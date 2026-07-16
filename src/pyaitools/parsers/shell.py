"""Shell tool parsers (shellcheck, shfmt)."""

from __future__ import annotations

from pyaitools.models import Finding, Location, Severity
from pyaitools.parsers.base import register
from pyaitools.parsers.patterns import JsonListParser


@register
class ShellcheckParser(JsonListParser):
    id = "shellcheck_json"

    def parse_one(self, item: dict) -> Finding:
        level = item.get("level", "warning")
        severity = Severity.ERROR if level in {"error", "warning"} else Severity.INFO
        return Finding(
            rule_id=f"SC{item.get('code', 0)}",
            severity=severity,
            message=item.get("message", "shellcheck finding"),
            location=Location(
                file=item.get("file", ""),
                line=item.get("line"),
                column=item.get("column"),
                end_line=item.get("endLine"),
                end_column=item.get("endColumn"),
            ),
        )
