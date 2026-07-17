"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _isolate_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop inherited git env vars (e.g. from pre-commit during git commit)."""
    for name in _GIT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
