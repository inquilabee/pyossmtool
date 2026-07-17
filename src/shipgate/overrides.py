"""Per-run CLI overrides for check and suite execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunOverrides:
    target: str | None = None
    config_path: Path | None = None
    include_globs: list[str] = field(default_factory=list)

    def include_for(self, check_include: list[str]) -> list[str]:
        if self.include_globs:
            return list(self.include_globs)
        return list(check_include)
