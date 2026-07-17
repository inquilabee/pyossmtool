"""Tests for the all-lint suite membership."""

from __future__ import annotations

from shipgate.models import CheckMode
from shipgate.registry import Registry

_FORMAT_BANNED = (
    "ruff.format",
    "mdformat.format",
    "shfmt.format",
    "yamlfmt.format",
    "ruff.format.apply",
    "mdformat.apply",
    "shfmt.apply",
    "yamlfmt.apply",
)


def test_all_lint_excludes_format_includes_pytest_and_optional() -> None:
    registry = Registry()
    suite = registry.get_suite("all-lint")
    ids = [ref.id for ref in suite.checks]

    assert "pytest.test" in ids
    assert "pytest.coverage" in ids
    assert "mutmut.run" in ids
    assert "sourcery.review" in ids
    assert "ruff.lint" in ids
    assert "ruff.unused" in ids

    for banned in _FORMAT_BANNED:
        assert banned not in ids

    assert "mutants/" in suite.ignore_paths

    for ref in suite.checks:
        assert registry.get_check(ref.id).mode == CheckMode.CHECK
