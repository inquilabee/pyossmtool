# Contributing to shipgate

Thanks for helping improve the orchestrator. This guide is for people changing **shipgate itself**, not for using it in an application repo. For install and everyday usage, see [README.md](README.md).

## Development setup

```bash
uv sync --all-groups
make install-hooks   # optional: run make check-commit before each commit
make check-commit
make build
```

After changing `suite:` in `shipgate.yaml`, re-run `shipgate install` so the managed tool set matches the new checklist.

Useful Make targets:

| Target | Purpose |
|--------|---------|
| `make install-hooks` | install git pre-commit hook (`.pre-commit-config.yaml`) |
| `make check-commit` | format check, ruff, unit tests |
| `make test` | unit tests (`-m "not integration"`) |
| `make integration` | wheel install / slower tests |
| `make build` | sdist + wheel |
| `make publish-check` | build and sanity-check the wheel |

## Architecture (short)

Runtime assets live inside the package:

```text
src/shipgate/bundle/
  catalog/tools/     # installable binaries + files: globs
  catalog/checks/    # check/format variants (mode: check | format)
  suites/            # named check lists
  defaults/          # bundled configs, gates, allowlists
```

Model: **Tool → Check → Suite**. The CLI filters checks by `mode` (`check` vs `format`).

## Adding a tool

1. Add `src/shipgate/bundle/catalog/tools/<id>.yaml`  
   Include `install`, `binary`, and `files:` globs (empty list means pass the directory target through).
2. Add one or more checks under `src/shipgate/bundle/catalog/checks/` with `mode: check` or `mode: format`.
3. Optionally add a parser under `src/shipgate/parsers/` and register it (see existing `@register` classes).
4. Reference the check ids from a suite YAML under `src/shipgate/bundle/suites/`.

Keep catalog YAML consistent: clear `id`, correct `parser`, and `mode` so `shipgate check` never runs write/format-apply checks.

### Parser reuse

| Parser | Use when |
| --- | --- |
| `noop` | Apply-mode checks; success is exit-code only |
| `gate_json` | Custom gates writing structured JSON via `lib.sh` or `gate_sdk` |
| `script_text` | Legacy gates printing `FAIL …` lines |
| `cli_text` | Generic line-oriented stderr/stdout |
| Tool JSON/text parsers | Tool emits a stable machine-readable format (see `parsers/`) |

### Project-local catalog extensions

Consumers can add tools and checks under:

```text
.shipgate/catalog/tools/<id>.yaml
.shipgate/catalog/checks/<id>.yaml
.shipgate/suites/<id>.yaml
```

Scaffold helpers:

```bash
shipgate tool init mylinter --binary mylinter --files '**/*.py'
shipgate gate init my-policy --python
```

Config convention: optional `<tool_id>.yaml` at repo root or `.shipgate/configs/<tool_id>.yaml`.

## Project-local script gates

Consumers can scaffold gates with `shipgate gate init`. Bundled gate helpers live under `src/shipgate/bundle/defaults/gates/`. When changing that framework, update both the shell lib and any related Python policy helpers under `src/shipgate/policy/`.

## Quality bar

Framework code quality is part of the product:

- Prefer small modules and typed public APIs
- Keep pure logic separate from I/O where practical
- Add or update tests with behavior changes
- Default tests stay deterministic; mark wheel/network/binary-heavy tests `@pytest.mark.integration`

## Releases

Publishing is automated on pushes to `main` via `.github/workflows/python-publish.yml` (Trusted Publishing).

1. Bump `version` in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Push to `main`

Re-pushing an already-published version fails the workflow on purpose.
