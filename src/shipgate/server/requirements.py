"""First-use requirements acknowledgement for the report server."""

from __future__ import annotations

import json
from pathlib import Path

from shipgate.models import utc_now


def requirements_path(primary: Path) -> Path:
    return Path(primary) / ".shipgate" / "server" / "requirements_ack.json"


def is_acknowledged(primary: Path) -> bool:
    return requirements_path(primary).is_file()


def acknowledge(primary: Path) -> None:
    path = requirements_path(primary)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"acknowledged_at": utc_now().isoformat()}
    path.write_text(json.dumps(payload), encoding="utf-8")
