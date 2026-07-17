# CHANGELOG

<!-- markdownlint-disable MD024 -->

## Unreleased

## v0.1.0

### Added

- **Breaking rename:** package and CLI are now `shipgate` (runtime dir `.shipgate/`, config `shipgate.yaml`). Legacy `pyossmtool.yaml` and `.pyossmtool/` are read with a deprecation warning.
- `<tool_id>.yaml` and `.shipgate/configs/<tool_id>.yaml` config discovery in `auto` mode.
- CLI flags `--config`, `--include`, and suite-level `--target` overrides.
- Per-tool CLI aliases: `shipgate ruff lint --target src/`.
- Python gate SDK (`shipgate.gate_sdk.Gate`) and `shipgate gate init --python`.
- `shipgate tool init` for project-local tool catalog scaffolding.
- Check aliases (`shellcheck` → `shellcheck.check`).

### Changed

- Remediation hints prefer `shipgate format --check …` over raw tool commands where apply checks exist.
- `shipgate check --check` defaults `--target` from `shipgate.yaml` (falls back to `.`).

## v0.0.8

### Added

- Report-server findings table: clickable expandable rows with GitHub-style line-numbered snippets for file context and multiline tool-failure output.
- Findings path search (file/folder substring filter) and paginated code findings.
- Report-server footer with version and GitHub repo link.
- Semgrep scan uses bundled `p/python` and `p/security-audit` rulesets by default.

### Changed

- Findings message column stays clamped when a detail snippet is available; full tracebacks render in the expandable panel.
- Tool version parsing covers more CLI output shapes on the tool docs page.

### Fixed

- Semgrep config resolution skips `--config` when the check uses repo-local bundled rules.

## v0.0.7

### Fixed

- Bundled default `ignore-paths` (`.venv/`, `.shipgate/`, `reports/`, etc.) apply to every suite so minimal configs do not scan virtualenvs and report dirs.
- Ruff format parser handles `Would reformat:` lines before the `.py` suffix heuristic (fixes `Would:?:` compact output).
- Ty ignore materialization filters gitignore-only glob syntax (`*$py.class`, `*.py,cover`, `**_cache**`, etc.) so `ty.check` does not fail with invalid-glob exit 2.
- Report server reuses the primary checkout when the selected branch is already checked out (fixes same-branch run failures).

### Changed

- README quick-start recommends `suite: standard` and documents bundled ignore defaults.
- `python-quality` suite documents ignore profile/paths for parity with `standard`.

## v0.0.6

### Added

- Pre-commit hook (`make install-hooks`) running `make check-commit` before each commit.
- djlint Jinja formatter in pre-commit for report-server templates.

### Changed

- Report-server HTML templates reformatted with djlint.

## v0.0.5

### Added

- Report server (`shipgate server`) with optional `shipgate[server]` install extra.
- `all-lint` suite for full lint/analysis plus tests without format check or apply.
- Auto-refresh overview when a report-server run finishes.

### Changed

- Docs and examples recommend `env: managed` for tool isolation; `env: project` is not advertised.
- Report-server pytest/mutmut runs use the project environment; resolver prefers `VIRTUAL_ENV`.
- Findings message columns wrap so long stack traces do not force horizontal scroll.
- Slimmer README report-server section.

## v0.0.4

### Changed

- Support Python 3.14 (`requires-python = ">=3.11,<3.15"`); CI matrix covers 3.11–3.14.
- Enable Ruff McCabe complexity rule `C901` (`C90`, max-complexity = 10) in project and bundled defaults.
- Bundled Ruff default `line-length` set to `120` (matches project config).

## v0.0.3

### Changed

- `install` and `format` default to `suite:` from `shipgate.yaml` (same as `check`); `--suite` is an override.
- README rewritten as a shorter developer-first guide with yaml-first suite selection.

## v0.0.2

### Added

- Error formatters for failure stderr (`error-format` / `error-formatters` in `shipgate.yaml`).
- Built-ins: `json` (default), `log`, `text`, `compact`, `github`; custom `finding_line` and `jq`.

## v0.0.1

### Added

- First public release as **shipgate** on PyPI.
- Bundled catalog, defaults, and suites inside the installable wheel.
- CLI commands `check` (report-only) and `format` (apply formatters).
- Tool-level `files:` globs with default target `.` and always-on `.gitignore`.
- Project-local npm installs under `.shipgate/tools/npm/` (no global npm).
- Script-gate scaffolding and managed pip tool installs.
