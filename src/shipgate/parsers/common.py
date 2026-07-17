"""Shared parser helpers."""

from __future__ import annotations

import re

from shipgate.models import Finding, FixHint, Location, Severity

RANK_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}

_SEVERITY_BY_NAME = {
    "warning": Severity.WARNING,
    "info": Severity.INFO,
}


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def finding_from_dict(item: dict) -> Finding:
    return Finding(
        rule_id=item.get("rule_id", "gate"),
        severity=_severity_from_dict(item),
        message=item.get("message", "script gate finding"),
        location=_location_from_dict(item),
        snippet=item.get("snippet"),
        fix=_fix_from_dict(item),
    )


def _location_from_dict(item: dict) -> Location | None:
    loc = item.get("location")
    if not isinstance(loc, dict) or not loc.get("file"):
        return None
    return Location(
        file=loc.get("file", ""),
        line=loc.get("line"),
        column=loc.get("column"),
        end_line=loc.get("end_line"),
        end_column=loc.get("end_column"),
    )


def _severity_from_dict(item: dict) -> Severity:
    severity_raw = str(item.get("severity", "error")).lower()
    return _SEVERITY_BY_NAME.get(severity_raw, Severity.ERROR)


def _fix_from_dict(item: dict) -> FixHint | None:
    fix_data = item.get("fix")
    if not isinstance(fix_data, dict):
        return None
    return FixHint(
        description=fix_data.get("description"),
        command=fix_data.get("command"),
    )
