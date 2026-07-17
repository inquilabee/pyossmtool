"""shipgate command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from shipgate.cli_aliases import register_tool_aliases
from shipgate.error_formatters import ErrorFormatter, format_report_file, resolve_error_formatter
from shipgate.gates import lib_path, scaffold_gate
from shipgate.installer import Installer
from shipgate.models import CheckMode, FailureReport, ProjectConfig
from shipgate.overrides import RunOverrides
from shipgate.registry import Registry
from shipgate.runner import Runner
from shipgate.tool_scaffold import scaffold_tool

app = typer.Typer(help="Quality-gate orchestrator for AI-assisted development")
list_app = typer.Typer(help="List catalog entries")
gate_app = typer.Typer(help="Shell script gate framework")
gates_app = typer.Typer(help="Gate library utilities")
tool_app = typer.Typer(help="Scaffold project-local tools")
app.add_typer(list_app, name="list")
app.add_typer(gate_app, name="gate")
app.add_typer(gates_app, name="gates")
app.add_typer(tool_app, name="tool")


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
        typer.echo(f"{check.id}\t{check.tool}\t{check.name}\t{check.mode.value}\t({origin})")


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
    python: bool = typer.Option(False, "--python", help="Scaffold a Python gate script"),
) -> None:
    """Scaffold a gate under .shipgate/gates/ and register it in the catalog."""
    project_root = _project_root()
    try:
        script_path, catalog_path = scaffold_gate(project_root, name, description, python=python)
    except FileExistsError as exc:
        typer.echo(f"SETUP {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Created gate script: {script_path.relative_to(project_root)}")
    typer.echo(f"Created catalog check: {catalog_path.relative_to(project_root)}")
    typer.echo("")
    typer.echo("Add the check to shipgate.yaml:")
    typer.echo(f"  - id: {catalog_path.stem}")
    typer.echo("")
    typer.echo("Run it:")
    typer.echo(f"  shipgate check --check {catalog_path.stem} --target .")


@tool_app.command("init")
def tool_init(
    name: str = typer.Argument(..., help="Tool name (e.g. mylinter)"),
    binary: str | None = typer.Option(None, "--binary", help="Executable name on PATH"),
    files: list[str] | None = typer.Option(None, "--files", help="File globs (repeatable)"),
    parser: str = typer.Option("cli_text", "--parser", help="Output parser id"),
) -> None:
    """Scaffold a project-local tool and check under .shipgate/catalog/."""
    project_root = _project_root()
    try:
        tool_path, check_path, config_path = scaffold_tool(
            project_root,
            name,
            binary=binary,
            files=files,
            parser=parser,
        )
    except FileExistsError as exc:
        typer.echo(f"SETUP {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Created tool catalog: {tool_path.relative_to(project_root)}")
    typer.echo(f"Created check catalog: {check_path.relative_to(project_root)}")
    if config_path is not None:
        typer.echo(f"Created config stub: {config_path.relative_to(project_root)}")
    typer.echo("")
    typer.echo("Add the check to shipgate.yaml:")
    typer.echo(f"  - id: {check_path.stem}")


@app.command("schema")
def export_schema() -> None:
    typer.echo(json.dumps(FailureReport.model_json_schema(), indent=2))


@app.command("install")
def install(
    suite: str | None = typer.Option(
        None,
        "--suite",
        help="Suite whose tools to install (default: suite from shipgate.yaml)",
    ),
) -> None:
    registry = _registry()
    project_root = _project_root()
    project_config = registry.load_project_config(project_root)
    suite_id = suite or (project_config.suite if project_config else None)
    if not suite_id:
        typer.echo("SETUP provide --suite or set suite: in shipgate.yaml", err=True)
        raise typer.Exit(code=2)
    installer = Installer(registry, project_root)
    try:
        installer.install_suite(suite_id)
    except Exception as exc:
        typer.echo(f"SETUP {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _cli_options(
    suite: str | None,
    check: str | None,
    target: str | None,
    config: Path | None,
    include: list[str] | None,
    fail_fast: bool,
    verbose: bool,
) -> tuple[RunOverrides, str | None, str | None, bool, bool]:
    overrides = RunOverrides(
        target=target,
        config_path=config,
        include_globs=list(include or []),
    )
    return overrides, suite, check, fail_fast, verbose


@app.command("check")
def check_cmd(
    suite: str | None = typer.Option(
        None,
        "--suite",
        help="Suite id to run (default: suite from shipgate.yaml)",
    ),
    check: str | None = typer.Option(None, "--check", help="Single check id to run"),
    target: str | None = typer.Option(None, "--target", help="Target path"),
    config: Path | None = typer.Option(None, "--config", help="Config file override"),
    include: list[str] | None = typer.Option(None, "--include", help="Include glob (repeatable)"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at first failure"),
    verbose: bool = typer.Option(False, "--verbose", help="Print commands and keep raw artifacts on success"),
) -> None:
    """Report-only quality checks (no file writes from formatters)."""
    overrides, suite, check, fail_fast, verbose = _cli_options(
        suite, check, target, config, include, fail_fast, verbose
    )
    raise typer.Exit(code=_execute(CheckMode.CHECK, suite, check, overrides, fail_fast, verbose))


@app.command("server")
def server_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    open_browser: bool = typer.Option(False, "--open"),
) -> None:
    """Local quality report UI (requires the server install extra)."""
    try:
        from shipgate.server.cli import run_server
    except ImportError as exc:
        typer.echo("SETUP install server extras: pip install 'shipgate[server]'", err=True)
        raise typer.Exit(code=2) from exc
    run_server(host=host, port=port, open_browser=open_browser)


@app.command("format")
def format_cmd(
    suite: str | None = typer.Option(
        None,
        "--suite",
        help="Suite id to run (default: suite from shipgate.yaml)",
    ),
    check: str | None = typer.Option(None, "--check", help="Single check id to run"),
    target: str | None = typer.Option(None, "--target", help="Target path"),
    config: Path | None = typer.Option(None, "--config", help="Config file override"),
    include: list[str] | None = typer.Option(None, "--include", help="Include glob (repeatable)"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at first failure"),
    verbose: bool = typer.Option(False, "--verbose", help="Print commands and keep raw artifacts on success"),
) -> None:
    """Apply formatters / autofix checks that write to the tree."""
    overrides, suite, check, fail_fast, verbose = _cli_options(
        suite, check, target, config, include, fail_fast, verbose
    )
    raise typer.Exit(code=_execute(CheckMode.FORMAT, suite, check, overrides, fail_fast, verbose))


def _execute(
    mode: CheckMode,
    suite: str | None,
    check: str | None,
    overrides: RunOverrides,
    fail_fast: bool,
    verbose: bool,
) -> int:
    registry = _registry()
    project_root = _project_root()
    project_config = registry.load_project_config(project_root)
    try:
        formatter = resolve_error_formatter(project_config)
    except (KeyError, ValueError, RuntimeError) as exc:
        typer.echo(f"SETUP {exc}", err=True)
        return 2
    runner = Runner(registry, project_root, verbose=verbose)

    if check:
        return _run_single_check(runner, check, overrides, suite, project_config, mode, formatter)
    return _run_suite(runner, suite, project_config, mode, fail_fast, formatter, overrides)


def _run_suite(
    runner: Runner,
    suite: str | None,
    project_config: ProjectConfig | None,
    mode: CheckMode,
    fail_fast: bool,
    formatter: ErrorFormatter,
    overrides: RunOverrides,
) -> int:
    suite_id = suite or (project_config.suite if project_config else None)
    if not suite_id:
        typer.echo("SETUP provide --suite or set suite: in shipgate.yaml", err=True)
        return 2
    try:
        suite_result = runner.run_suite(
            suite_id,
            project_config=project_config,
            fail_fast=fail_fast,
            mode=mode,
            overrides=overrides,
        )
    except KeyError as exc:
        typer.echo(f"SETUP {exc}", err=True)
        return 2
    return _emit_suite_result(suite_result, formatter)


def _run_single_check(
    runner: Runner,
    check: str,
    overrides: RunOverrides,
    suite: str | None,
    project_config: ProjectConfig | None,
    mode: CheckMode,
    formatter: ErrorFormatter,
) -> int:
    target = overrides.target or (project_config.target if project_config else None) or "."
    check_def = runner.registry.get_check(check)
    if check_def.mode != mode:
        typer.echo(
            f"SETUP check '{check}' has mode={check_def.mode.value}; use shipgate {check_def.mode.value}",
            err=True,
        )
        return 2
    result = runner.run_check(
        check,
        target=target,
        suite_id=suite or (project_config.suite if project_config else None),
        project_config=project_config,
        overrides=overrides,
    )
    return _exit_for_check_result(result, formatter)


def _exit_for_check_result(result, formatter: ErrorFormatter) -> int:
    if result.error:
        typer.echo(f"SETUP {result.error}", err=True)
        return 2
    if result.passed:
        return 0
    _emit_failed_check(result, formatter)
    return 1


def _emit_suite_result(suite_result, formatter: ErrorFormatter) -> int:
    if suite_result.passed:
        return 0
    for result in suite_result.results:
        _emit_failed_check(result, formatter)
    return 1


def _emit_failed_check(result, formatter: ErrorFormatter) -> None:
    if result.passed:
        return
    if result.error:
        typer.echo(f"SETUP {result.check_id}: {result.error}", err=True)
        return
    if not result.report_path:
        return
    try:
        text = format_report_file(result.report_path, formatter)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"SETUP failed to format report for {result.check_id}: {exc}", err=True)
        typer.echo(f"FAIL {result.check_id} -> {result.report_path}", err=True)
        return
    typer.echo(text, err=True)


def main() -> None:
    register_tool_aliases(app, _registry(), _execute)
    app()


_TYPER_COMMANDS = (
    list_tools,
    list_checks,
    list_suites,
    gates_lib_path,
    gate_init,
    tool_init,
    export_schema,
    install,
    check_cmd,
    server_cmd,
    format_cmd,
)


if __name__ == "__main__":
    main()
