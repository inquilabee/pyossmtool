"""Parser behavior for mutmut and pydeps noisy tool output."""

from __future__ import annotations

from shipgate.parsers.analysis import PydepsCyclesParser
from shipgate.parsers.prose import MutmutParser
from shipgate.registry import Registry


def test_pydeps_tool_uses_directory_target_not_file_globs() -> None:
    tool = Registry().get_tool("pydeps")
    assert tool.files == []


def test_pydeps_parser_collapses_usage_dump() -> None:
    stderr = """usage: pydeps [-h] [--debug]
              [--show-cycles]
              fname
pydeps: error: unrecognized arguments: src/a.py src/b.py
"""
    findings = PydepsCyclesParser().parse("", stderr)
    assert len(findings) == 1
    assert findings[0].rule_id == "pydeps-error"
    assert "unrecognized arguments" in findings[0].message
    assert findings[0].location is None


def test_pydeps_parser_keeps_real_cycle_lines() -> None:
    stdout = "a -> b -> a\nother.cycle.path\n"
    findings = PydepsCyclesParser().parse(stdout, "")
    assert len(findings) == 1
    assert findings[0].rule_id == "import-cycle"
    assert findings[0].message == "a -> b -> a"


def test_pydeps_parser_collapses_module_name_essay() -> None:
    stderr = """Cannot analyze '.': 'main-0d6e4079e367' is not a valid Python module name.

Technical reason:
  pydeps works by generating a synthetic 'dummy' module
Fix:
  Rename the offending file or directory
"""
    findings = PydepsCyclesParser().parse("", stderr)
    assert len(findings) == 1
    assert findings[0].rule_id == "pydeps-error"
    assert "main-0d6e4079e367" in findings[0].message
    assert findings[0].location is None


def test_mutmut_parser_skips_spinner_and_extracts_collect_error() -> None:
    stdout = """
⠋ Generating mutants
⠙ Generating mutants
    done in 954ms (30 files mutated, 0 ignored, 0 unmodified)

==================================== ERRORS ====================================
______________________ ERROR collecting tests/test_cli.py ______________________
ImportError while importing test module.
E   ModuleNotFoundError: No module named 'typer'
failed to collect stats. runner returned 1
"""
    findings = MutmutParser().parse(stdout, "")
    assert len(findings) >= 1
    collect = [f for f in findings if f.rule_id == "collect-error"]
    assert len(collect) == 1
    assert collect[0].location is not None
    assert collect[0].location.file == "tests/test_cli.py"
    assert not any("Generating mutants" in f.message for f in findings)
