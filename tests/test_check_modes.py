"""Tests for check/format mode filtering."""

from __future__ import annotations

from shipgate.models import CheckMode, SuiteCheckRef
from shipgate.registry import Registry
from shipgate.runner import Runner


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


def test_all_suite_contains_every_check() -> None:
    registry = Registry()
    suite = registry.get_suite("all")
    suite_ids = {ref.id for ref in suite.checks}
    assert suite_ids == set(registry.checks)
