"""Ruff parsers."""

from __future__ import annotations

from pyaitools.models import Finding, FixHint, Location, Severity
from pyaitools.parsers.base import register
from pyaitools.parsers.patterns import JsonListParser


@register
class RuffJsonParser(JsonListParser):
    id = "ruff_json"

    def parse_one(self, item: dict) -> Finding:
        filename = item.get("filename")
        location = None
        if filename:
            location = Location(
                file=filename,
                line=item.get("location", {}).get("row"),
                column=item.get("location", {}).get("column"),
                end_line=item.get("end_location", {}).get("row"),
                end_column=item.get("end_location", {}).get("column"),
            )
        code = item.get("code", "ruff")
        return Finding(
            rule_id=code,
            severity=Severity.ERROR if str(code).startswith("E") else Severity.WARNING,
            message=item.get("message", "ruff finding"),
            location=location,
            snippet=item.get("message"),
            fix=FixHint(
                description="Apply ruff auto-fix",
                command=f"ruff check --fix {filename}",
            )
            if filename
            else None,
        )
