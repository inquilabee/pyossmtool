# pyossmtool 0.0.1 Design

**Date:** 2026-07-16\
**Status:** Approved for implementation\
**Goal:** Publish `pyossmtool==0.0.1` to public PyPI with a working wheel, full catalog, and a stable public CLI.

## Product identity

| Surface | Name |
|---------|------|
| PyPI distribution | `pyossmtool` |
| Import package | `pyossmtool` |
| CLI entry point | `pyossmtool` |
| Consumer config | `pyossmtool.yaml` |
| Project state dir | `.pyossmtool/` |
| Version | `0.0.1` |

Hard cut: no `pyossmtool` compatibility shims in 0.0.1.

## Architecture

Retain **Tool → Check → Suite**:

- **Tool** — installable binary, config/ignore materialization, and **file globs** (`files:`) describing what it operates on.
- **Check** — one gate variant (lint vs format-check vs format-apply), with `mode: check | format`.
- **Suite** — ordered list of checks plus optional root `target` (default `.`).

Silent on success; structured `FailureReport` JSON on failure.

## Packaging

Runtime assets ship **inside** the installable package:

```text
src/pyossmtool/bundle/
  catalog/tools/*.yaml
  catalog/checks/*.yaml
  suites/*.yaml
  defaults/**/*
```

`BUNDLE_ROOT` resolves from `Path(__file__).parent / "bundle"` so a clean `pip install` works without a git checkout. Wheel `package-data` must include `bundle/**/*`.

## Targeting and ignores

- Default scan root: **`.`** (optional single `target:` override in config or suite).
- No consumer `targets:` map in 0.0.1.
- Tool defs declare globs (`**/*.py`, `**/*.{yml,yaml}`, …).
- Check-level `include:` is an optional narrowing override.
- Empty globs → pass the directory target through to tools that accept dirs.
- Empty match set after expansion → silent pass.
- **Always** apply `.gitignore` (plus suite/project ignore profiles and paths).

## CLI

| Command | Behavior |
|---------|----------|
| `pyossmtool check` | Report-only: runs checks with `mode: check` |
| `pyossmtool format` | Write/format: runs checks with `mode: format` |

Also: `install`, `list`, `gate`, `gates`, `schema`. Public `run` is removed.

Formatters expose separate check-mode (`--check` / lint / diff) and format-mode (apply) catalog entries. Suites used by `check` must not include format-apply checks.

## Catalog scope

Ship the **full** existing catalog (all tools, checks, suites). Default consumer experience may use a focused suite (`python-quality`); the package still contains everything for extendibility.

## Installer

- Pip tools → managed venv under `.pyossmtool/tools/venv`.
- npm tools → **project-local** under `.pyossmtool/tools/npm/` (never `npm install -g`).
- System tools → warn if missing; fail at run time if unresolved.

## Quality charter (non-negotiable)

Framework code quality is a product feature:

- Clarity over cleverness; single responsibility; pure logic separate from I/O.
- Typed public APIs; pydantic models at YAML/CLI boundaries.
- Prefer small modules; extract helpers instead of growing god-modules.
- Default tests deterministic (`-m "not integration"`); wheel smoke marked `integration`; `filterwarnings = ["error"]`.
- Every commit leaves tests green; no “ship now, clean later.”
- Never claim completion without running the relevant verification commands.

## Out of scope for 0.0.1

- Multi-root typed `targets:` map
- Compatibility with the taken PyPI name `pyossmtool`
- Consumer pre-commit / Trunk productization
- Renaming the git checkout directory
