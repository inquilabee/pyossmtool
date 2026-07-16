# ResLab Quality Tools Inventory

Exploration of `/home/dayhatt/workspace/res-lab` — the tools used to **slow down** and **keep AI in check** during development. This is read-only analysis; no changes were made to reslab.

## Summary

ResLab does **not** use only 3 tools. It runs a layered quality pipeline across **pre-commit**, **pre-push**, and **CI**. The three we prototyped first (`ruff`, `radon`, `jscpd`) are only part of the picture.

## Tool inventory

| Tool | Purpose | When it runs | Output (typical) |
|------|---------|--------------|------------------|
| **ruff** | Lint + format; includes McCabe C901 (`max-complexity = 5`) | pre-commit, CI | `reports/ruff.txt` |
| **ty** | Static type checking (Astral) | pre-commit, CI | `reports/ty.txt`, `reports/ty.junit.xml` |
| **shellcheck** | Shell script lint | pre-commit (via Trunk) | Trunk/CI output |
| **semgrep** | Architecture import boundaries + pandas patterns | pre-commit (arch), CI (pandas) | `reports/semgrep.json` |
| **bandit** | Python security scan | pre-commit, CI | JSON via hook |
| **radon** | Cyclomatic complexity + maintainability index | CI | `reports/radon.json`, `reports/radon-cc.txt`, `reports/maintainability.json` |
| **jscpd** | Duplicate code detection | CI | `reports/jscpd-*/jscpd-report.json` |
| **deadcode** + **vulture** + ruff F401/F841 | Dead / unused code | CI | `reports/deadcode-scan.txt` |
| **pydeps** | Import graph / cycle detection | CI | `reports/pydeps/YYYY-MM-DD/` |
| **mutmut** | Mutation testing | CI | `reports/mutation/` |
| **pytest + coverage** | Tests; 85% floor on `src/reslab` | pre-commit (subset), CI | `reports/coverage.xml`, `reports/htmlcov/` |
| **gitleaks** | Secret scanning | pre-commit | hook output |
| **codespell** | Spelling | pre-commit | gate script |
| **mdformat / markdownlint** | Markdown style | pre-commit | hook output |
| **yamlfmt / yamllint** | YAML style | pre-commit | hook output |
| **hadolint** | Dockerfile lint | Trunk | Trunk output |
| **module-size-check** | File size limits | pre-commit | gate script |
| **module-private-vars-check** | Private var conventions | pre-commit | gate script |
| **folder-breadth-check** | Package breadth limits | CI | `reports/folder-breadth.json` |
| **frontend-check** | Frontend lint/build | pre-commit | gate script |

Sources: `docs/engineering/platform/build-pipeline.md`, `pyproject.toml`, `.pre-commit-config.yaml`, `.trunk/trunk.yaml`, `bin/gates/*.sh`.

## How reslab wires tools together

1. **Declarative config** — `pyproject.toml` holds ruff, ty, coverage, mutmut, deadcode, pydeps settings.
1. **Gate scripts** — `bin/gates/*.sh` wrap each tool with paths, thresholds, and exit codes.
1. **Pre-commit** — `.pre-commit-config.yaml` + Trunk (`bin/gates/trunk-check-pre-commit.sh`) for fast feedback.
1. **CI pipeline** — `make pipeline` / `bin/gates/pre-push-pipeline.sh` runs the full enforcing suite.
1. **Reports directory** — machine-readable JSON/XML + human-readable `.txt` under `reports/`.

## pyossmtool prototype status

Configs created under `tools/` and runnable via `run_tool.py`:

| Tool ID | Config | Demo run |
|---------|--------|----------|
| `ruff-linter` | `tools/ruff-linter.yaml` | ✅ `sample_files/` |
| `radon-complexity` | `tools/radon-complexity.yaml` | ✅ `sample_files/` |
| `jscpd-duplication` | `tools/jscpd-duplication.yaml` | ✅ `sample_files/` |
| `ty-check` | `tools/ty-check.yaml` | ✅ `sample_files/` |
| `shellcheck` | `tools/shellcheck.yaml` | ✅ `sample_files/example.sh` |
| `bandit-security` | `tools/bandit-security.yaml` | ✅ `sample_files/` |

### Example usage

```bash
source venv/bin/activate
python3 run_tool.py --tool-id ty-check --target-path sample_files/
python3 run_tool.py --tool-id shellcheck --target-path sample_files/example.sh
python3 run_tool.py --tool-id ruff-linter --target-path sample_files/
```

Reports land in `reports/<tool-id>/<timestamp>/raw_output.*`.

## Recommended next steps for pyossmtool

1. **Mirror reslab's full tool list** — add YAML configs for semgrep, deadcode, pydeps, bandit (done), coverage, mutmut.
1. **Shared config bundle** — one `quality-suite.yaml` that lists tool IDs, target paths, and thresholds (shareable across repos).
1. **Aggregate report** — single `reports/summary.json` combining pass/fail from all tools (reslab does this via `bin/dev/quality-trend.sh` / `summary.json`).
1. **Exit-code policy** — distinguish advisory vs enforcing tools (reslab uses fail-fast pre-commit but report-only deadcode in review).

## Why this matters for AI guardrails

These tools act as **automated critics** that catch what AI often skips:

- **ty** — wrong types, missing annotations
- **shellcheck** — broken shell scripts AI generates for ops/setup
- **ruff / radon** — complexity and style drift
- **jscpd** — copy-paste duplication across files
- **semgrep** — architectural boundary violations
- **mutation / coverage** — tests that look good but don't assert behavior

Standardizing them behind config + `run_tool.py` makes the guardrails **portable** — share a YAML bundle, point at any repo, get comparable reports.
