"""Tests for check/format mode filtering."""

from __future__ import annotations

from pyossmtool.models import CheckMode, SuiteCheckRef
from pyossmtool.registry import Registry
from pyossmtool.runner import Runner


def test_check_skips_format_mode_checks() -> None:
    registry = Registry()
    runner = Runner(registry)
    refs = [
        SuiteCheckRef(id="ruff.format"),
        SuiteCheckRef(id="ruff.format.apply"),
    ]
    filtered = runner._filter_check_refs(refs, CheckMode.CHECK)
    assert [ref.id for ref in filtered] == ["ruff.format"]


def test_format_runs_only_format_mode_checks() -> None:
    registry = Registry()
    runner = Runner(registry)
    refs = [
        SuiteCheckRef(id="ruff.format"),
        SuiteCheckRef(id="ruff.format.apply"),
        SuiteCheckRef(id="mdformat.apply"),
    ]
    filtered = runner._filter_check_refs(refs, CheckMode.FORMAT)
    assert [ref.id for ref in filtered] == ["ruff.format.apply", "mdformat.apply"]


def test_format_suite_contains_apply_checks() -> None:
    registry = Registry()
    suite = registry.get_suite("format")
    assert suite.checks
    for ref in suite.checks:
        assert registry.get_check(ref.id).mode == CheckMode.FORMAT
