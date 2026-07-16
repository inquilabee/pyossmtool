# Parser class registry and shared patterns

**Date:** 2026-07-16  
**Status:** Approved for planning  
**Goals:** (1) registry / discoverability, (2) shared parsing patterns  
**Out of scope:** runtime finding-invariant validation, catalog `parser:` id renames

## Problem

Parsers are plain functions wired by a hand-maintained dict in `parsers/__init__.py`. Shared shapes (JSON list → findings, line regex → findings, policy JSON) are duplicated. Adding a parser means editing multiple places with no shared contract.

## Decision

Adopt **Approach A**: flat registry of small parser classes, with pattern base classes for shared logic. Keep existing catalog `parser:` ids unchanged (`shellcheck_json`, `ruff_json`, …).

## Design

### Contract

```python
class Parser(ABC):
    id: ClassVar[str]
    uses_stderr: ClassVar[bool] = True
    needs_check: ClassVar[bool] = False

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        ...

    def parse_one(self, item: Any) -> Finding | None:
        """Optional: map one record/match to a Finding. Not all parsers use this."""
```

- Runner always calls `parse(...)`.
- `parse_one` is for item-shaped dialects (JSON list items, regex matches).
- `needs_check=True` for radon/jscpd policy parsers.
- `uses_stderr` documents whether stderr is consulted (default True for text tools).

### Pattern bases

| Base | Role |
|------|------|
| `JsonListParser` | Load JSON array (stdout or stderr); map each item via `parse_one` |
| `LineRegexParser` | Compile `pattern`; each line match → `parse_one(match)` |
| `DiffTextParser` | Line scan with current-file tracking for format diffs |
| `PolicyJsonParser` | JSON object + `check.policy` thresholds |
| `FallbackTextParser` | Free-text lines / fallback finding |

### Registry

```python
REGISTRY: dict[str, type[Parser]] = {}

def register(cls: type[Parser]) -> type[Parser]:
    REGISTRY[cls.id] = cls
    return cls
```

`parse_output(check, stdout, stderr)` becomes:

```python
parser_cls = REGISTRY[check.parser]  # KeyError → ValueError unknown parser
kwargs = {"check": check} if parser_cls.needs_check else {}
return parser_cls().parse(stdout, stderr, **kwargs)
```

Import side-effect: loading `pyossmtool.parsers` imports concrete modules so `@register` runs.

### Layout

```text
src/pyossmtool/parsers/
  base.py           # Parser, register, REGISTRY
  patterns.py       # JsonListParser, LineRegexParser, DiffTextParser, PolicyJsonParser, FallbackTextParser
  ruff.py
  shell.py          # shellcheck, shfmt
  analysis.py       # ty, bandit, radon, jscpd, semgrep, deadcode, vulture, pydeps, pytest
  format_md_yaml.py # mdformat, yamlfmt (or keep in format.py)
  prose.py          # gitleaks, codespell, markdownlint, yamllint, hadolint, mutmut, sourcery
  gates.py          # cli_text, gate_json, script_text, noop
  common.py         # strip_ansi, finding_from_dict, RANK_ORDER (unchanged helpers)
  __init__.py       # parse_output + import concrete modules
```

Exact module split can group by domain; each concrete class must set `id` matching catalog.

### Compatibility

- Catalog YAML: no changes.
- Public API: keep `from pyossmtool.parsers import parse_output`.
- Tests: update imports that called private `_parse_*` / module functions; prefer `REGISTRY[id]().parse(...)` or `parse_output`.

### Non-goals (later)

- Post-parse finding validators
- Renaming `parser:` ids
- Deep hierarchy per tool vendor

## Success criteria

1. Every current catalog `parser:` id resolves via `REGISTRY`.
2. Existing pytest suite passes; golden-style tests for at least one pattern base + one concrete parser.
3. No hand-maintained `_parser_handlers()` dict.
4. Complexity policy still A-only on `src/pyossmtool` for radon.cc / radon.mi.
