"""Parser ABC and registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pyaitools.models import CheckDef, Finding


class Parser(ABC):
    id: ClassVar[str]
    needs_check: ClassVar[bool] = False

    @abstractmethod
    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        raise NotImplementedError


REGISTRY: dict[str, type[Parser]] = {}


def register(cls: type[Parser]) -> type[Parser]:
    if not getattr(cls, "id", None):
        raise ValueError(f"Parser {cls.__name__} missing id")
    if cls.id in REGISTRY:
        raise ValueError(f"Duplicate parser id: {cls.id}")
    REGISTRY[cls.id] = cls
    return cls
