# pyossmtool

Portable quality-gate orchestrator for Python-first repositories. Inspired by Trunk and pre-commit: opinionated defaults, little required configuration, silent on success, structured failure reports for humans and AI agents.

## Install

```bash
pip install pyossmtool
# or
uv add --dev pyossmtool
```

Requires Python 3.11–3.13.

## Quick start

Create `pyossmtool.yaml` in your repo:

```yaml
suite: python-quality
env: auto
target: .
configs:
  mode: auto
```

Install tool binaries for that suite, then run:

```bash
pyossmtool install --suite python-quality
pyossmtool format                 # apply formatters (suite: format)
pyossmtool check                  # report-only (suite from pyossmtool.yaml)
```

- **`check`** — report-only (linters, type checkers, format `--check` variants)
- **`format`** — writes files (formatter apply checks)

On failure, pyossmtool exits non-zero and writes a JSON failure report under `reports/failures/`. Inspect the schema with `pyossmtool schema`.

## How targeting works

- Default scan root is `.` (override with `target:` in config or suite).
- Each tool declares `files:` globs (e.g. `**/*.py`). Matching files are discovered under the target.
- `.gitignore` is always applied. Extra ignore profiles/paths can be added in suite or project config.

## Adding a tool

1. Add `src/pyossmtool/bundle/catalog/tools/<id>.yaml` (install method, binary, `files:`).
1. Add one or more checks under `catalog/checks/` with `mode: check` or `mode: format`.
1. Optionally add a parser class under `pyossmtool.parsers` and register it.
1. Reference the check ids from a suite YAML.

Project-local script gates: `pyossmtool gate init <name>`.

## Development

```bash
uv sync --all-groups
make check-commit
make build
```

## License

MIT
