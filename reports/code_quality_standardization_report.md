# pyossmtool Architecture

Quality-gate orchestrator for AI-assisted development. Standardizes tools behind a **Tool → Check → Suite** model with **silent success**, **structured failure reports**, and **layered configuration**.

## Portable consumer config

Copy [`pyossmtool.yaml.example`](../../pyossmtool.yaml.example) to your repo as `pyossmtool.yaml`:

```yaml
suite: standard
env: auto
targets:
  python: src/
  tests: tests/
  coverage: src/
  shell: bin/
  markdown: .
  yaml: .
  prose: .
  repo: .
  dockerfile: Dockerfile
configs:
  mode: auto
```

No repo-specific paths ship in the default config. The `demo` suite alone uses `sample_files/` for local development fixtures.

## Design layers

| Layer | Location | Role |
|-------|----------|------|
| **Tool** | `catalog/tools/` | Installable binary + version pin |
| **Check** | `catalog/checks/` | Variant gate (`ruff.lint` vs `ruff.format`) |
| **Suite** | `suites/` | Bundled check lists + default targets |
| **Consumer** | `pyossmtool.yaml` | Suite choice, scan roots, config mode |

## Format checks

| Check | Tool | Target key |
|-------|------|------------|
| `ruff.format` | ruff | python |
| `shfmt.format` | shfmt | shell |
| `mdformat.format` | mdformat | markdown |
| `yamlfmt.format` | yamlfmt | yaml |

Suite `formatting` runs all format-only checks. Suite `standard` is the recommended default for new projects — full reslab-equivalent CLI coverage. Suite `extended` adds slow checks (`mutmut`, `sourcery`).

## Layered configuration

Precedence (per tool):

1. **Repo-native** — `ruff.toml`, `pyproject.toml` `[tool.ruff]`, `[tool.ty]`, etc. (native discovery, no `--config` injected)
1. **`pyossmtool.yaml` `configs.paths`** — when `configs.mode: paths`
1. **Bundled defaults** — `defaults/configs/` when repo has no config (`configs.mode: auto` or `bundled`)

| Mode | Behavior |
|------|----------|
| `auto` | Repo config if present; else bundled opinionated defaults |
| `bundled` | Always use `defaults/configs/*` |
| `paths` | Use explicit paths from `configs.paths` |

Bundled files:

- `defaults/configs/ruff.toml`
- `defaults/configs/ty.toml`
- `defaults/configs/yamlfmt.yaml`
- `defaults/configs/yamllint.yaml`
- `defaults/configs/markdownlint.json`
- `defaults/semgrep/python-quality.yml`

## Execution contract

| Outcome | CLI | Files |
|---------|-----|-------|
| Pass | silent, exit 0 | none |
| Fail | `FAIL <check> -> reports/failures/.../report.json` | FailureReport v1 |
| Setup error | `SETUP ...`, exit 2 | none |

## CLI

```bash
pip install -e .
pyossmtool install --suite standard
pyossmtool run                    # uses pyossmtool.yaml
pyossmtool run --suite demo       # dev fixtures only
pyossmtool run --suite formatting
pyossmtool run --suite extended   # includes mutmut + sourcery
pyossmtool list checks
pyossmtool schema
```

## Catalog summary

### Tools (21)

| Tool | Install | Purpose |
|------|---------|---------|
| ruff | pip | Lint, format, unused imports |
| ty | pip | Type checking |
| radon | pip | Complexity / maintainability |
| bandit | pip | Security scan |
| jscpd | npm | Duplication detection |
| shellcheck | system | Shell lint |
| shfmt | system | Shell format |
| mdformat | pip | Markdown format |
| markdownlint | npm | Markdown lint |
| yamlfmt | system | YAML format |
| yamllint | pip | YAML lint |
| semgrep | pip | Pattern / architecture rules |
| deadcode | pip | Unused code |
| vulture | pip | Dead code (high confidence) |
| pydeps | pip | Import cycle detection |
| pytest | pip | Tests + coverage |
| gitleaks | system | Secret scanning |
| codespell | pip | Spelling |
| hadolint | system | Dockerfile lint |
| mutmut | pip | Mutation testing (extended suite) |
| sourcery | pip | Code review (extended suite) |

### Checks (24)

**Python:** `ruff.lint`, `ruff.format`, `ruff.unused`, `ty.check`, `bandit.scan`, `radon.cc`, `radon.mi`, `jscpd.duplication`, `semgrep.scan`, `deadcode.scan`, `vulture.scan`, `pydeps.cycles`, `pytest.test`, `pytest.coverage`, `mutmut.run`, `sourcery.review`

**Shell:** `shellcheck`, `shfmt.format`

**Docs/config:** `mdformat.format`, `markdownlint.check`, `yamlfmt.format`, `yamllint.check`, `codespell.spelling`

**Repo:** `gitleaks.secrets`, `hadolint.dockerfile`

### Suites

| Suite | Purpose |
|-------|---------|
| `standard` | **Recommended for new projects** — full reslab CLI tool parity |
| `python-quality` | ruff lint + format + ty on `src/` |
| `formatting` | all format checks |
| `extended` | standard + mutmut + sourcery |
| `reslab-parity` | alias for standard (reference mapping) |
| `demo` | internal `sample_files/` fixtures only |

### Not yet portable (reslab custom bash gates)

Reslab also runs project-specific gates (`module-size-check`, `folder-breadth-check`, `frontend-check`, etc.). Use **script gates** (see `defaults/gates/README.md`):

```bash
pyossmtool gate init module-size --description "Cap module line counts"
# add `- id: gate.module-size` to pyossmtool.yaml checks
```

Wrap existing scripts with `parser: script_text`, or migrate to `gate_fail` / `gate_finish` for structured `FailureReport` JSON.

## Design invariants

1. One tool, many checks
1. Explicit dependency graph (suite → checks → tools)
1. Success is silent
1. Failure is structured (`FailureReport` v1)
1. Hybrid env (`auto` / `managed` / `project`)
1. Repo configs beat bundled defaults
1. Portable `pyossmtool.yaml` — no sample paths in consumer config
