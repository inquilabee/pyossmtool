"""Additional CLI and gate coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from shipgate.cli import app
from shipgate.gates import (
    default_report_path,
    gate_check_id,
    gate_script_path,
    lib_path,
    scaffold_gate,
)
from shipgate.models import CheckMode, CheckResult, SuiteResult


def test_list_subcommands_emit_catalog_rows() -> None:
    runner = CliRunner()
    for args in (["list", "tools"], ["list", "checks"], ["list", "suites"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert result.output.strip()


def test_schema_exports_failure_report_json() -> None:
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert schema["title"] == "FailureReport"


def test_gates_lib_path_command() -> None:
    result = CliRunner().invoke(app, ["gates", "lib-path"])
    assert result.exit_code == 0
    assert result.output.strip() == str(lib_path())


def test_gate_init_scaffolds_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["gate", "init", "module-size", "-d", "Limit module size"])
    assert result.exit_code == 0
    script = tmp_path / ".shipgate/gates/module-size.sh"
    catalog = tmp_path / ".shipgate/catalog/checks/gate.module-size.yaml"
    assert script.is_file()
    assert catalog.is_file()
    assert "module-size" in result.output


def test_gate_init_refuses_existing_script(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(app, ["gate", "init", "dup"])
    result = CliRunner().invoke(app, ["gate", "init", "dup"])
    assert result.exit_code == 2
    assert "SETUP" in result.output


def test_check_requires_suite_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 2


def test_check_single_defaults_target_when_omitted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: standard\n", encoding="utf-8")
    from shipgate.registry import Registry

    registry = Registry()
    check_def = registry.get_check("ruff.lint")
    with patch("shipgate.cli.Runner") as runner_cls:
        runner_cls.return_value.registry.get_check.return_value = check_def
        runner_cls.return_value.run_check.return_value = CheckResult(check_id="ruff.lint", passed=True)
        result = CliRunner().invoke(app, ["check", "--check", "ruff.lint"])
    assert result.exit_code == 0
    call_kwargs = runner_cls.return_value.run_check.call_args.kwargs
    assert call_kwargs["target"] == "."


def test_check_suite_success_is_silent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: standard\n", encoding="utf-8")
    suite_result = SuiteResult(suite_id="standard", passed=True, results=[])
    with patch("shipgate.cli.Runner") as runner_cls:
        runner_cls.return_value.run_suite.return_value = suite_result
        result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert result.output == ""


def test_check_emits_formatter_output_on_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: standard\nerror_format: text\n", encoding="utf-8")
    failed = CheckResult(
        check_id="ruff.lint",
        passed=False,
        report_path=str(tmp_path / "report.json"),
    )
    suite_result = SuiteResult(suite_id="standard", passed=False, results=[failed])
    with (
        patch("shipgate.cli.Runner") as runner_cls,
        patch(
            "shipgate.cli.format_report_file",
            return_value="FAIL ruff.lint\n",
        ),
    ):
        runner_cls.return_value.run_suite.return_value = suite_result
        result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 1
    assert "FAIL ruff.lint" in result.output


def test_format_command_delegates_to_runner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: format\n", encoding="utf-8")
    suite_result = SuiteResult(suite_id="format", passed=True, results=[])
    with patch("shipgate.cli.Runner") as runner_cls:
        runner = runner_cls.return_value
        runner.run_suite.return_value = suite_result
        result = CliRunner().invoke(app, ["format"])
    assert result.exit_code == 0
    runner.run_suite.assert_called_once()
    assert runner.run_suite.call_args.kwargs["mode"] == CheckMode.FORMAT


def test_gate_helpers_slugify_names() -> None:
    assert gate_check_id("Module Size!") == "gate.module-size"
    assert gate_script_path("Module Size!") == ".shipgate/gates/module-size.sh"
    assert default_report_path("gate.demo") == ".shipgate/reports/gate.demo.json"


def test_scaffold_gate_writes_executable_script(tmp_path: Path) -> None:
    script_path, catalog_path = scaffold_gate(tmp_path, "demo-gate", "Demo gate")
    assert script_path.exists()
    assert catalog_path.exists()
    assert oct(script_path.stat().st_mode & 0o111) != "0o0"
    assert "gate_init" in script_path.read_text(encoding="utf-8")


def test_install_surfaces_installer_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: standard\n", encoding="utf-8")
    with patch("shipgate.cli.Installer") as installer_cls:
        installer_cls.return_value.install_suite.side_effect = RuntimeError("boom")
        result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 2
    assert "SETUP boom" in result.output


def test_check_unknown_suite_returns_setup_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shipgate.yaml").write_text("suite: missing-suite\n", encoding="utf-8")
    with patch("shipgate.cli.Runner") as runner_cls:
        runner_cls.return_value.run_suite.side_effect = KeyError("missing-suite")
        result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 2
    assert "SETUP" in result.output
