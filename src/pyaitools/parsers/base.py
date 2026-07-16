"""Parser ABC and registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pyaitools.models import CheckDef, Finding


class Parser(ABC):
    id: ClassVar[str]
    uses_stderr: ClassVar[bool] = True
    needs_check: ClassVar[bool] = False

    @abstractmethod
    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError

    def parse_one(self, item: Any) -> Finding | None:
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_one")


REGISTRY: dict[str, type[Parser]] = {}


def register(cls: type[Parser]) -> type[Parser]:
    if not getattr(cls, "id", None):
        raise ValueError(f"Parser {cls.__name__} missing id")
    if cls.id in REGISTRY:
        raise ValueError(f"Duplicate parser id: {cls.id}")
    REGISTRY[cls.id] = cls
    return cls
