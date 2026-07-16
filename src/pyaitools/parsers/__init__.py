"""Parse native tool output into normalized Finding objects."""

from __future__ import annotations

from collections.abc import Callable

from pyaitools.models import CheckDef, Finding
from pyaitools.parsers import (
    analysis_parsers,
    format_parsers,
    gate_parsers,
    prose_parsers,
    python_parsers,
)

_CHECK_AWARE_PARSERS = frozenset({"radon_cc_json", "radon_mi_json", "jscpd_json"})
_STDERR_PARSERS = frozenset(
    {
        "ruff_format_text",
        "ty_concise",
        "shellcheck_json",
        "shfmt_diff",
        "mdformat_text",
        "yamlfmt_text",
        "deadcode_text",
        "vulture_text",
        "pydeps_cycles_text",
        "pytest_text",
        "gitleaks_json",
        "codespell_text",
        "markdownlint_json",
        "yamllint_text",
        "hadolint_json",
        "mutmut_text",
        "sourcery_text",
        "cli_text",
        "gate_json",
        "script_text",
    }
)


def _parser_handlers() -> dict[str, Callable[..., list[Finding]]]:
    return {
        "ruff_json": python_parsers.parse_ruff_json,
        "ruff_format_text": python_parsers.parse_ruff_format,
        "ty_concise": analysis_parsers.parse_ty,
        "shellcheck_json": format_parsers.parse_shellcheck,
        "bandit_json": analysis_parsers.parse_bandit,
        "radon_cc_json": analysis_parsers.parse_radon_cc,
        "radon_mi_json": analysis_parsers.parse_radon_mi,
        "jscpd_json": analysis_parsers.parse_jscpd,
        "shfmt_diff": format_parsers.parse_shfmt_diff,
        "mdformat_text": format_parsers.parse_mdformat,
        "yamlfmt_text": format_parsers.parse_yamlfmt,
        "semgrep_json": analysis_parsers.parse_semgrep,
        "deadcode_text": analysis_parsers.parse_deadcode,
        "vulture_text": analysis_parsers.parse_vulture,
        "pydeps_cycles_text": analysis_parsers.parse_pydeps_cycles,
        "pytest_text": analysis_parsers.parse_pytest,
        "gitleaks_json": prose_parsers.parse_gitleaks,
        "codespell_text": prose_parsers.parse_codespell,
        "markdownlint_json": prose_parsers.parse_markdownlint,
        "yamllint_text": prose_parsers.parse_yamllint,
        "hadolint_json": prose_parsers.parse_hadolint,
        "mutmut_text": prose_parsers.parse_mutmut,
        "sourcery_text": prose_parsers.parse_sourcery,
        "cli_text": gate_parsers.parse_cli_text,
        "gate_json": gate_parsers.parse_gate_json,
        "script_text": gate_parsers.parse_script_text,
        "noop": lambda _stdout, _stderr: [],
    }


def parse_output(check: CheckDef, stdout: str, stderr: str) -> list[Finding]:
    handler = _parser_handlers().get(check.parser)
    if handler is None:
        raise ValueError(f"Unknown parser: {check.parser}")
    if check.parser in _CHECK_AWARE_PARSERS:
        return handler(stdout, check)
    if check.parser in _STDERR_PARSERS:
        return handler(stdout, stderr)
    return handler(stdout)
