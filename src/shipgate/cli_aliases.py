"""Per-tool Typer aliases generated from the check catalog."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import typer

from shipgate.models import CheckMode
from shipgate.overrides import RunOverrides
from shipgate.registry import Registry


def _verb_from_check_id(check_id: str) -> str:
    if "." in check_id:
        return check_id.rsplit(".", 1)[-1]
    return "check"


def register_tool_aliases(app: typer.Typer, registry: Registry, execute_fn) -> None:
    """Register ``shipgate <tool> <verb>`` commands that delegate to check/format."""
    by_tool: dict[str, list[tuple[str, str, CheckMode]]] = defaultdict(list)
    for check_id, check in registry.checks.items():
        by_tool[check.tool].append((check_id, _verb_from_check_id(check_id), check.mode))

    for tool_id, entries in sorted(by_tool.items()):
        if tool_id == "script":
            continue
        tool_app = typer.Typer(help=f"Run {tool_id} checks", invoke_without_command=True)
        registered_verbs: set[str] = set()

        for check_id, verb, mode in entries:
            if verb in registered_verbs:
                continue
            registered_verbs.add(verb)
            _register_verb_command(tool_app, tool_id, verb, check_id, mode, execute_fn)

        app.add_typer(tool_app, name=tool_id)


def _register_verb_command(
    tool_app: typer.Typer,
    tool_id: str,
    verb: str,
    check_id: str,
    mode: CheckMode,
    execute_fn,
) -> None:
    def _handler(
        ctx: typer.Context,
        target: str | None = typer.Option(None, "--target", help="Scan target"),
        config: Path | None = typer.Option(None, "--config", help="Config file override"),
        include: list[str] = typer.Option(None, "--include", help="Include glob (repeatable)"),
        _check_id: str = check_id,
        _mode: CheckMode = mode,
    ) -> None:
        if ctx.invoked_subcommand is not None:
            return
        overrides = RunOverrides(
            target=target,
            config_path=config,
            include_globs=list(include or []),
        )
        raise typer.Exit(
            code=execute_fn(
                _mode,
                suite=None,
                check=_check_id,
                overrides=overrides,
                fail_fast=False,
                verbose=False,
            )
        )

    tool_app.command(verb, help=f"Run {check_id}")(_handler)
