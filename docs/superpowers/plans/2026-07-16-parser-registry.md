# Parser Registry and Pattern Bases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace function-based parsers with a registered class hierarchy (pattern bases + concrete parsers) while keeping catalog `parser:` ids and `parse_output` unchanged for callers.

**Architecture:** `Parser` ABC + `@register` into `REGISTRY`; pattern bases (`JsonListParser`, `LineRegexParser`, `DiffTextParser`, `PolicyJsonParser`, `FallbackTextParser`) hold shared logic; concrete classes set `id` matching catalog keys. `parse_output` looks up `REGISTRY[check.parser]` and calls `.parse(...)`.

**Tech Stack:** Python 3.11+, pydantic `Finding`/`CheckDef`, pytest, existing pyossmtool runner.

**Spec:** `docs/superpowers/specs/2026-07-16-parser-registry-design.md`

## Global Constraints

- Keep catalog `parser:` string ids unchanged (e.g. `shellcheck_json`, `ruff_json`, `ty_concise`).
- Keep public `from pyossmtool.parsers import parse_output`.
- Do not add finding-invariant validation in this plan.
- Preserve radon A-only / existing quality gates on `src/pyossmtool`.
- Prefer thin classes; extract helpers if a method would exceed complexity rank A.

## File map

| File | Responsibility |
|------|----------------|
| `src/pyossmtool/parsers/base.py` | `Parser` ABC, `REGISTRY`, `register` |
| `src/pyossmtool/parsers/patterns.py` | Shared pattern bases |
| `src/pyossmtool/parsers/ruff.py` | `ruff_json`, `ruff_format_text` |
| `src/pyossmtool/parsers/shell.py` | `shellcheck_json`, `shfmt_diff` |
| `src/pyossmtool/parsers/analysis.py` | ty, bandit, radon, jscpd, semgrep, deadcode, vulture, pydeps, pytest |
| `src/pyossmtool/parsers/format_text.py` | `mdformat_text`, `yamlfmt_text` |
| `src/pyossmtool/parsers/prose.py` | gitleaks, codespell, markdownlint, yamllint, hadolint, mutmut, sourcery |
| `src/pyossmtool/parsers/gates.py` | `cli_text`, `gate_json`, `script_text`, `noop` |
| `src/pyossmtool/parsers/common.py` | Keep helpers (`strip_ansi`, `finding_from_dict`, `RANK_ORDER`) |
| `src/pyossmtool/parsers/__init__.py` | Import modules for registration; export `parse_output`, `REGISTRY` |
| Delete after migration | `python_parsers.py`, `analysis_parsers.py`, `format_parsers.py`, `prose_parsers.py`, `gate_parsers.py` |
| `tests/test_parser_registry.py` | Registry + pattern + parse_output smoke tests |
| `tests/test_script_gates.py` | Point at gate parser classes / `parse_output` |

---

### Task 1: Base registry and pattern scaffolding

**Files:**
- Create: `src/pyossmtool/parsers/base.py`
- Create: `src/pyossmtool/parsers/patterns.py`
- Create: `tests/test_parser_registry.py`
- Modify: (none yet for production callers)

**Interfaces:**
- Consumes: `CheckDef`, `Finding` from `pyossmtool.models`
- Produces: `Parser`, `register`, `REGISTRY`, `JsonListParser`, `LineRegexParser`, `DiffTextParser`, `PolicyJsonParser`, `FallbackTextParser`

- [ ] **Step 1: Write failing registry tests**

```python
# tests/test_parser_registry.py
from __future__ import annotations

import json

from pyossmtool.models import CheckDef, Finding, Severity, SuccessCriteria
from pyossmtool.parsers.base import REGISTRY, Parser, register
from pyossmtool.parsers.patterns import JsonListParser


def test_register_adds_parser_id() -> None:
    @register
    class _DemoParser(Parser):
        id = "_demo_only"

        def parse(self, stdout: str, stderr: str = "", *, check=None) -> list[Finding]:
            return []

    assert "_demo_only" in REGISTRY
    assert REGISTRY["_demo_only"] is _DemoParser
    REGISTRY.pop("_demo_only", None)


def test_json_list_parser_maps_items() -> None:
    class _Items(JsonListParser):
        id = "_json_demo"

        def parse_one(self, item: dict) -> Finding:
            return Finding(
                rule_id=item["id"],
                severity=Severity.ERROR,
                message=item["msg"],
            )

    findings = _Items().parse(json.dumps([{"id": "X", "msg": "hello"}]), "")
    assert len(findings) == 1
    assert findings[0].rule_id == "X"
    assert findings[0].message == "hello"
```

- [ ] **Step 2: Run tests — expect fail (modules missing)**

Run: `uv run pytest tests/test_parser_registry.py -v`  
Expected: FAIL with import error for `pyossmtool.parsers.base` / `patterns`

- [ ] **Step 3: Implement `base.py`**

```python
# src/pyossmtool/parsers/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pyossmtool.models import CheckDef, Finding

REGISTRY: dict[str, type[Parser]] = {}


def register(cls: type[Parser]) -> type[Parser]:
    if not getattr(cls, "id", None):
        raise ValueError(f"Parser {cls.__name__} missing id")
    if cls.id in REGISTRY:
        raise ValueError(f"Duplicate parser id: {cls.id}")
    REGISTRY[cls.id] = cls
    return cls


class Parser(ABC):
    id: ClassVar[str]
    uses_stderr: ClassVar[bool] = True
    needs_check: ClassVar[bool] = False

    @abstractmethod
    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError

    def parse_one(self, item: Any) -> Finding | None:
        raise NotImplementedError(f"{type(self).__name__} does not implement parse_one")
```

Note: define `Parser` before `REGISTRY` type hint resolves — use `from __future__ import annotations` and quote or reorder: put `REGISTRY: dict[str, type["Parser"]] = {}` after class, or use:

```python
REGISTRY: dict[str, type[Parser]] = {}  # with future annotations OK after class body
```

Put `REGISTRY` and `register` **after** the `Parser` class definition to avoid forward-ref confusion at runtime for `register`'s annotation.

- [ ] **Step 4: Implement `patterns.py` (JsonListParser minimum for the test)**

```python
# src/pyossmtool/parsers/patterns.py
from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from pyossmtool.models import CheckDef, Finding
from pyossmtool.parsers.base import Parser


class JsonListParser(Parser):
    """JSON array in stdout (or stderr if stdout empty) → parse_one per item."""

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        payload_text = stdout.strip() or stderr.strip()
        if not payload_text:
            return []
        payload = json.loads(payload_text)
        findings: list[Finding] = []
        for item in payload:
            finding = self.parse_one(item)
            if finding is not None:
                findings.append(finding)
        return findings


class LineRegexParser(Parser):
    pattern: ClassVar[re.Pattern[str]]

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        text = stdout or stderr
        findings: list[Finding] = []
        for line in text.splitlines():
            match = self.pattern.match(line.strip())
            if not match:
                continue
            finding = self.parse_one(match)
            if finding is not None:
                findings.append(finding)
        return findings


class DiffTextParser(Parser):
    """Override parse(); helpers for current-file tracking live as methods subclasses use."""

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError


class PolicyJsonParser(Parser):
    needs_check: ClassVar[bool] = True

    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError


class FallbackTextParser(Parser):
    def parse(
        self, stdout: str, stderr: str = "", *, check: CheckDef | None = None
    ) -> list[Finding]:
        raise NotImplementedError
```

- [ ] **Step 5: Run tests — expect pass**

Run: `uv run pytest tests/test_parser_registry.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pyossmtool/parsers/base.py src/pyossmtool/parsers/patterns.py tests/test_parser_registry.py
git commit -m "$(cat <<'EOF'
Add parser ABC, registry, and JsonListParser pattern base.

EOF
)"
```

---

### Task 2: Migrate JSON-list parsers (shellcheck, bandit, ruff json)

**Files:**
- Create: `src/pyossmtool/parsers/shell.py`
- Create: `src/pyossmtool/parsers/ruff.py`
- Create: `src/pyossmtool/parsers/analysis.py` (start with bandit)
- Modify: `tests/test_parser_registry.py` (add id smoke asserts after registration imports)
- Reference behavior: current `format_parsers.parse_shellcheck`, `python_parsers.parse_ruff_json`, `analysis_parsers.parse_bandit`

**Interfaces:**
- Consumes: `JsonListParser`, `register`, helpers from `common`
- Produces: registered ids `shellcheck_json`, `ruff_json`, `bandit_json`

- [ ] **Step 1: Write failing tests for registered ids**

```python
def test_shellcheck_parser_registered_and_parses() -> None:
    from pyossmtool.parsers import shell  # noqa: F401
    from pyossmtool.parsers.base import REGISTRY

    payload = json.dumps(
        [{"code": 2086, "level": "warning", "message": "Double quote", "file": "a.sh", "line": 1}]
    )
    findings = REGISTRY["shellcheck_json"]().parse(payload, "")
    assert findings[0].rule_id == "SC2086"
    assert findings[0].location is not None
    assert findings[0].location.file == "a.sh"
```

- [ ] **Step 2: Run test — expect fail (not registered)**

Run: `uv run pytest tests/test_parser_registry.py::test_shellcheck_parser_registered_and_parses -v`  
Expected: FAIL KeyError or import error

- [ ] **Step 3: Implement `ShellcheckParser` and `RuffJsonParser` / `BanditParser` by moving logic from existing functions into `parse_one`**

Port message/location mapping verbatim from current helpers. Example shellcheck:

```python
@register
class ShellcheckParser(JsonListParser):
    id = "shellcheck_json"

    def parse_one(self, item: dict) -> Finding:
        level = item.get("level", "warning")
        severity = Severity.ERROR if level in {"error", "warning"} else Severity.INFO
        return Finding(
            rule_id=f"SC{item.get('code', 0)}",
            severity=severity,
            message=item.get("message", "shellcheck finding"),
            location=Location(
                file=item.get("file", ""),
                line=item.get("line"),
                column=item.get("column"),
                end_line=item.get("endLine"),
                end_column=item.get("endColumn"),
            ),
        )
```

Same for ruff JSON and bandit using existing `_ruff_json_finding` / bandit loop bodies.

- [ ] **Step 4: Run focused tests — expect pass**

Run: `uv run pytest tests/test_parser_registry.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyossmtool/parsers/shell.py src/pyossmtool/parsers/ruff.py src/pyossmtool/parsers/analysis.py tests/test_parser_registry.py
git commit -m "$(cat <<'EOF'
Register shellcheck, ruff JSON, and bandit JsonList parsers.

EOF
)"
```

---

### Task 3: Migrate line-regex and policy parsers

**Files:**
- Modify: `src/pyossmtool/parsers/analysis.py`
- Modify: `src/pyossmtool/parsers/prose.py` (create)
- Modify: `src/pyossmtool/parsers/patterns.py` (complete `LineRegexParser` summary hooks if needed; implement `PolicyJsonParser.parse` skeleton used by radon)

**Interfaces:**
- Consumes: `LineRegexParser`, `PolicyJsonParser`, `RANK_ORDER` from `common`
- Produces: ids `ty_concise`, `codespell_text`, `yamllint_text`, `deadcode_text`, `vulture_text`, `radon_cc_json`, `radon_mi_json`, `jscpd_json`

- [ ] **Step 1: Add failing test for ty line parser**

```python
def test_ty_parser_parses_concise_line() -> None:
    from pyossmtool.parsers import analysis  # noqa: F401
    from pyossmtool.parsers.base import REGISTRY

    line = "src/a.py:1:2: error: Unknown name\n"
    findings = REGISTRY["ty_concise"]().parse(line, "")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.file == "src/a.py"
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest tests/test_parser_registry.py::test_ty_parser_parses_concise_line -v`  
Expected: FAIL

- [ ] **Step 3: Port ty, codespell, yamllint, deadcode, vulture onto `LineRegexParser` (or subclass with extra fallback like current `parse_ty` / `parse_deadcode`)**

If fallback summary findings are needed, override `parse()` to call `super().parse(...)` then append fallback — keep complexity low by extracting helpers.

- [ ] **Step 4: Port radon.cc / radon.mi / jscpd onto `PolicyJsonParser`**

```python
class PolicyJsonParser(Parser):
    needs_check = True

    def parse(self, stdout: str, stderr: str = "", *, check: CheckDef | None = None) -> list[Finding]:
        if check is None:
            raise ValueError(f"{self.id} requires check")
        if not stdout.strip():
            return []
        return self.parse_payload(json.loads(stdout), check)

    def parse_payload(self, payload: dict, check: CheckDef) -> list[Finding]:
        raise NotImplementedError
```

Move existing radon/jscpd logic into `parse_payload`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_parser_registry.py tests/test_script_gates.py -v`  
Expected: PASS (script gates still on old modules until Task 5)

- [ ] **Step 6: Commit**

```bash
git add src/pyossmtool/parsers/patterns.py src/pyossmtool/parsers/analysis.py src/pyossmtool/parsers/prose.py tests/test_parser_registry.py
git commit -m "$(cat <<'EOF'
Add line-regex and policy JSON parser classes.

EOF
)"
```

---

### Task 4: Migrate diff / fallback / remaining text parsers

**Files:**
- Modify: `src/pyossmtool/parsers/ruff.py` (`ruff_format_text`)
- Modify: `src/pyossmtool/parsers/shell.py` (`shfmt_diff`)
- Create: `src/pyossmtool/parsers/format_text.py` (`mdformat_text`, `yamlfmt_text`)
- Modify: `src/pyossmtool/parsers/prose.py` (gitleaks, markdownlint, hadolint, mutmut, sourcery)
- Modify: `src/pyossmtool/parsers/analysis.py` (semgrep, pydeps, pytest)
- Create: `src/pyossmtool/parsers/gates.py`

**Interfaces:**
- Consumes: `DiffTextParser` / `FallbackTextParser` / custom `parse()` where patterns do not fit
- Produces: all remaining catalog parser ids

- [ ] **Step 1: List required ids and assert coverage test**

```python
REQUIRED_PARSER_IDS = {
    "ruff_json", "ruff_format_text", "ty_concise", "shellcheck_json", "bandit_json",
    "radon_cc_json", "radon_mi_json", "jscpd_json", "shfmt_diff", "mdformat_text",
    "yamlfmt_text", "semgrep_json", "deadcode_text", "vulture_text", "pydeps_cycles_text",
    "pytest_text", "gitleaks_json", "codespell_text", "markdownlint_json", "yamllint_text",
    "hadolint_json", "mutmut_text", "sourcery_text", "cli_text", "gate_json", "script_text",
    "noop",
}

def test_all_catalog_parser_ids_registered() -> None:
    import pyossmtool.parsers as parsers_pkg  # ensures side-effect imports
    from pyossmtool.parsers.base import REGISTRY

    missing = REQUIRED_PARSER_IDS - set(REGISTRY)
    assert not missing, f"Missing parsers: {sorted(missing)}"
```

(Do not enable this assert until modules are imported from `__init__.py` in Task 5 — for this task, import each new module in the test or skip the full set until Task 5.)

- [ ] **Step 2: Port remaining parsers module-by-module, keeping behavior identical to current functions**

Priority order: ruff format, shfmt, mdformat, yamlfmt, semgrep, pydeps, pytest, prose leftovers, gates (`gate_json` uses `finding_from_dict`).

- [ ] **Step 3: Run unit tests for any new cases added**

Run: `uv run pytest tests/test_parser_registry.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/pyossmtool/parsers/
git commit -m "$(cat <<'EOF'
Port remaining tool parsers onto registered classes.

EOF
)"
```

---

### Task 5: Switch `parse_output` to registry; delete old modules

**Files:**
- Modify: `src/pyossmtool/parsers/__init__.py`
- Modify: `tests/test_script_gates.py`
- Modify: `tests/test_parser_registry.py` (enable full id coverage + `parse_output` smoke)
- Delete: `python_parsers.py`, `analysis_parsers.py`, `format_parsers.py`, `prose_parsers.py`, `gate_parsers.py`

**Interfaces:**
- Consumes: `REGISTRY`, all concrete modules
- Produces: `parse_output(check, stdout, stderr) -> list[Finding]` identical caller contract

- [ ] **Step 1: Write failing test that `parse_output` uses registry**

```python
from pyossmtool.models import CheckDef, SuccessCriteria
from pyossmtool.parsers import parse_output

def test_parse_output_ruff_json() -> None:
    check = CheckDef(
        id="ruff.lint",
        tool="ruff",
        name="Ruff",
        description="x",
        parser="ruff_json",
        success=SuccessCriteria(),
    )
    findings = parse_output(check, "[]", "")
    assert findings == []
```

- [ ] **Step 2: Rewrite `__init__.py`**

```python
from pyossmtool.models import CheckDef, Finding
from pyossmtool.parsers.base import REGISTRY
from pyossmtool.parsers import (  # side-effect registration
    analysis,
    format_text,
    gates,
    prose,
    ruff,
    shell,
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
```

Avoid unused-import lint by referencing modules in a tuple used for side effects, matching existing `_TYPER_COMMANDS` style if needed.

- [ ] **Step 3: Update `tests/test_script_gates.py` to use `REGISTRY["gate_json"]` / `script_text` or `parse_output`**

Replace:
`from pyossmtool.parsers.gate_parsers import parse_gate_json, parse_script_text`  
with registry or gates module class methods.

- [ ] **Step 4: Delete old function modules; run full tests**

Run: `uv run pytest tests/ -q`  
Expected: all PASS

- [ ] **Step 5: Run self-dogfood checks**

Run:

```bash
uv run pyossmtool run --check ruff.format --target src/
uv run pyossmtool run --check ruff.lint --target src/
uv run pyossmtool run --check ty.check --target src/
uv run pyossmtool run --check radon.cc --target src/
uv run pyossmtool run --check radon.mi --target src/
```

Expected: all PASS (silent / exit 0)

- [ ] **Step 6: Commit**

```bash
git add src/pyossmtool/parsers/ tests/
git commit -m "$(cat <<'EOF'
Switch parse_output to the parser registry and remove legacy modules.

EOF
)"
```

---

### Task 6: Docs touch-up (optional short note)

**Files:**
- Modify: `AGENTS.md` or existing README only if it documents parsers — skip if none mention the old function layout

- [ ] **Step 1: Grep docs for `parse_ruff` / `parsers.py` references**

Run: `rg -n "parse_ruff|_parser_handlers|parsers\\.py" -g '!docs/superpowers/**' .`  
If none, skip commit.

- [ ] **Step 2: If references exist, update to describe registry + `Parser.id`**

- [ ] **Step 3: Commit only if docs changed**

```bash
git add AGENTS.md  # or relevant files
git commit -m "$(cat <<'EOF'
Document parser registry layout.

EOF
)"
```

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| `Parser` ABC with `parse` / optional `parse_one` | Task 1 |
| `REGISTRY` + `@register` | Task 1 |
| Pattern bases JsonList / LineRegex / Diff / Policy / Fallback | Tasks 1–4 |
| Catalog ids unchanged | All tasks (no YAML edits) |
| `parse_output` public API | Task 5 |
| Delete hand-maintained handler dict | Task 5 |
| Tests for registry + at least one pattern | Tasks 1–2 |
| Quality gates still pass | Task 5 Step 5 |
| No finding-invariant validation | Explicitly omitted |

## Placeholder scan

No TBD/TODO steps; concrete code and commands included.

## Type consistency

- `parse(stdout, stderr="", *, check=None) -> list[Finding]` throughout
- `needs_check: ClassVar[bool]` gates whether `check=` is passed from `parse_output`
- Registry values are `type[Parser]`, instantiated per call: `parser_cls()`
