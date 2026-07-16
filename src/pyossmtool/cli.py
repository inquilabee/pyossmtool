"""pyossmtool command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from pyossmtool.gates import lib_path, scaffold_gate
from pyossmtool.installer import Installer
from pyossmtool.models import FailureReport
from pyossmtool.registry import Registry
from pyossmtool.runner import Runner

app = typer.Typer(help="Quality-gate orchestrator for AI-assisted development")
list_app = typer.Typer(help="List catalog entries")
gate_app = typer.Typer(help="Shell script gate framework")
gates_app = typer.Typer(help="Gate library utilities")
app.add_typer(list_app, name="list")
app.add_typer(gate_app, name="gate")
app.add_typer(gates_app, name="gates")


def _project_root() -> Path:
    return Path.cwd()


def _registry() -> Registry:
    return Registry(project_root=_project_root())


@list_app.command("tools")
def list_tools() -> None:
    registry = _registry()
    for tool in registry.tools.values():
        typer.echo(f"{tool.id}\t{tool.name}\t({tool.install.method.value})")


@list_app.command("checks")
def list_checks() -> None:
    registry = _registry()
    for check in registry.checks.values():
        origin = "project" if check.tool == "script" else "bundled"
        typer.echo(f"{check.id}\t{check.tool}\t{check.name}\t({origin})")


@list_app.command("suites")
def list_suites() -> None:
    registry = _registry()
    for suite in registry.suites.values():
        typer.echo(f"{suite.id}\t{suite.name}")


@gates_app.command("lib-path")
def gates_lib_path() -> None:
    """Print absolute path to defaults/gates/lib.sh for sourcing in scripts."""
    typer.echo(str(lib_path()))


@gate_app.command("init")
def gate_init(
    name: str = typer.Argument(..., help="Gate name (e.g. module-size)"),
    description: str = typer.Option("Project script gate", "--description", "-d"),
) -> None:
    """Scaffold a script gate under .pyossmtool/gates/ and register it in the catalog."""
    project_root = _project_root()
    try:
        script_path, catalog_path = scaffold_gate(project_root, name, description)
    except FileExistsError as exc:
        typer.echo(f"SETUP {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Created gate script: {script_path.relative_to(project_root)}")
    typer.echo(f"Created catalog check: {catalog_path.relative_to(project_root)}")
    typer.echo("")
    typer.echo("Add the check to pyossmtool.yaml:")
    typer.echo(f"  - id: {catalog_path.stem}")
    typer.echo("")
    typer.echo("Run it:")
    typer.echo(f"  pyossmtool run --check {catalog_path.stem} --target .")


@app.command("schema")
def export_schema() -> None:
    typer.echo(json.dumps(FailureReport.model_json_schema(), indent=2))


@app.command("install")
def install(
    suite: str = typer.Option("demo", "--suite", help="Suite whose tool dependencies to install"),
) -> None:
    registry = _registry()
    installer = Installer(registry, _project_root())
    try:
        installer.install_suite(suite)
    except Exception as exc:
        typer.echo(f"SETUP {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command("run")
def run(
    suite: str | None = typer.Option(None, "--suite", help="Suite id to run"),
    check: str | None = typer.Option(None, "--check", help="Single check id to run"),
    target: str | None = typer.Option(None, "--target", help="Target path for single check"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at first failure"),
    verbose: bool = typer.Option(False, "--verbose", help="Print commands and keep raw artifacts on success"),
) -> None:
    registry = _registry()
    project_root = _project_root()
    project_config = registry.load_project_config(project_root)
    runner = Runner(registry, project_root, verbose=verbose)

    if check:
        raise typer.Exit(code=_run_single_check(runner, check, target, suite, project_config))

    suite_id = suite or (project_config.suite if project_config else None)
    if not suite_id:
        typer.echo("SETUP provide --suite or create pyossmtool.yaml", err=True)
        raise typer.Exit(code=2)

    suite_result = runner.run_suite(suite_id, project_config=project_config, fail_fast=fail_fast)
    raise typer.Exit(code=_emit_suite_result(suite_result))


def _run_single_check(
    runner: Runner,
    check: str,
    target: str | None,
    suite: str | None,
    project_config,
) -> int:
    if not target:
        typer.echo("SETUP --target is required with --check", err=True)
        return 2
    result = runner.run_check(
        check,
        target=target,
        suite_id=suite or (project_config.suite if project_config else None),
        project_config=project_config,
    )
    return _exit_for_check_result(result)


def _exit_for_check_result(result) -> int:
    if result.error:
        typer.echo(f"SETUP {result.error}", err=True)
        return 2
    if result.passed:
        return 0
    typer.echo(f"FAIL {result.check_id} -> {result.report_path}", err=True)
    return 1


def _emit_suite_result(suite_result) -> int:
    if suite_result.passed:
        return 0
    for result in suite_result.results:
        _emit_failed_check(result)
    return 1


def _emit_failed_check(result) -> None:
    if result.passed:
        return
    if result.error:
        typer.echo(f"SETUP {result.check_id}: {result.error}", err=True)
        return
    if result.report_path:
        typer.echo(f"FAIL {result.check_id} -> {result.report_path}", err=True)


def main() -> None:
    app()


# Typer sub-app commands are registered via decorators; keep references for static analysis.
_TYPER_COMMANDS = (
    list_tools,
    list_checks,
    list_suites,
    gates_lib_path,
    gate_init,
    export_schema,
    install,
)


if __name__ == "__main__":
    main()
