"""Parse native tool output into normalized Finding objects."""

from __future__ import annotations

from pyossmtool.models import CheckDef, Finding
from pyossmtool.parsers.analysis import (
    BanditParser,
    DeadcodeParser,
    JscpdParser,
    PydepsCyclesParser,
    PytestParser,
    RadonCcParser,
    RadonMiParser,
    SemgrepParser,
    TyParser,
    VultureParser,
)
from pyossmtool.parsers.base import REGISTRY
from pyossmtool.parsers.format_text import MdformatParser, YamlfmtParser
from pyossmtool.parsers.gates import CliTextParser, GateJsonParser, NoopParser, ScriptTextParser
from pyossmtool.parsers.prose import (
    CodespellParser,
    GitleaksParser,
    HadolintParser,
    MarkdownlintParser,
    MutmutParser,
    SourceryParser,
    YamllintParser,
)
from pyossmtool.parsers.ruff import RuffFormatParser, RuffJsonParser
from pyossmtool.parsers.shell import ShellcheckParser, ShfmtDiffParser

# Keep registered classes referenced for static dead-code analysis.
_PARSER_CLASSES = (
    BanditParser,
    CliTextParser,
    CodespellParser,
    DeadcodeParser,
    GateJsonParser,
    GitleaksParser,
    HadolintParser,
    JscpdParser,
    MarkdownlintParser,
    MdformatParser,
    MutmutParser,
    NoopParser,
    PydepsCyclesParser,
    PytestParser,
    RadonCcParser,
    RadonMiParser,
    RuffFormatParser,
    RuffJsonParser,
    ScriptTextParser,
    SemgrepParser,
    ShellcheckParser,
    ShfmtDiffParser,
    SourceryParser,
    TyParser,
    VultureParser,
    YamllintParser,
    YamlfmtParser,
)


def parse_output(check: CheckDef, stdout: str, stderr: str) -> list[Finding]:
    try:
        parser_cls = REGISTRY[check.parser]
    except KeyError as exc:
        raise ValueError(f"Unknown parser: {check.parser}") from exc
    parser = parser_cls()
    if parser_cls.needs_check:
        return parser.parse(stdout, stderr, check=check)
    return parser.parse(stdout, stderr)


__all__ = ["REGISTRY", "parse_output", "_PARSER_CLASSES"]
