# Script gates

Shell-based policy checks integrated with pyossmtool failure reports.

## Bundled policy gates

| Check                      | Script                                  | Config                                            |
| -------------------------- | --------------------------------------- | ------------------------------------------------- |
| `gate.module-size`         | `defaults/gates/module-size.sh`         | `defaults/configs/gates/module-size.yaml`         |
| `gate.module-private-vars` | `defaults/gates/module-private-vars.sh` | `defaults/configs/gates/module-private-vars.yaml` |
| `gate.folder-breadth`      | `defaults/gates/folder-breadth.sh`      | `defaults/configs/gates/folder-breadth.yaml`      |
| `gate.acronym-allowlist`   | `defaults/gates/acronym-allowlist.sh`   | `defaults/configs/gates/acronym-allowlist.yaml`   |

Run via suite `policy` or as part of `standard`.

### Configure per repo

Each gate check declares where config lives (see `config:` on `catalog/checks/gate.*.yaml`):

```yaml
config:
  bundled: gates/module-size.yaml
  project_file: .pyossmtool/configs/gates/gate.module-size.yaml
  allowlist_bundled: module-size.txt
```

Resolution order: `configs.mode: paths` override → `project_file` if present → `bundled` under `defaults/configs/`.

Override bundled defaults by adding the project file:

```yaml
# .pyossmtool/configs/gates/gate.module-size.yaml
scan_roots:
  - src/myapp
  - scripts
portfolio_max_lines: 800
new_file_max_lines: 400
base_branch: main
allowlist_file: .pyossmtool/allowlists/module-size.txt
```

Or set explicit paths in `pyossmtool.yaml`:

```yaml
configs:
  mode: paths
  paths:
    gate.module-size: .pyossmtool/configs/gates/gate.module-size.yaml
```

Config keys are exported to gate scripts as `GATE_<KEY>` environment variables (lists become space-separated).

## Quick start (custom gate)

```bash
pyossmtool gate init module-size --description "Cap Python module line counts"
# edit .pyossmtool/gates/module-size.sh
# add to pyossmtool.yaml checks: - id: gate.module-size
pyossmtool run --check gate.module-size --target src/
```

## Layout

```text
.pyossmtool/
  gates/                 # your bash scripts
    module-size.sh
  catalog/
    checks/              # gate.<name>.yaml registrations
      gate.module-size.yaml
  reports/               # structured JSON written by lib.sh (gitignore this)
    gate.module-size.json
```

Project catalog entries **override** bundled checks with the same id.

## Gate script contract

1. Source `defaults/gates/lib.sh` via `pyossmtool gates lib-path`
1. Call `gate_init "<name>"`
1. Use `gate_fail` / `gate_warn` for findings
1. Call `gate_finish` (exits 0 on pass, 1 on fail)

### Environment (set by runner)

| Variable                    | Meaning                                                      |
| --------------------------- | ------------------------------------------------------------ |
| `PYOSSMTOOL_ROOT`            | Repository root                                              |
| `PYOSSMTOOL_TARGET`          | Resolved scan target for this check                          |
| `PYOSSMTOOL_CHECK_ID`        | Catalog check id                                             |
| `PYOSSMTOOL_REPORT`          | Path to write structured JSON findings                       |
| `PYOSSMTOOL_IGNORE_PROFILES` | Newline-separated ignore profile files (`.gitignore` syntax) |
| `PYOSSMTOOL_IGNORE_PATHS`    | Newline-separated repo-relative paths/globs to skip          |

Use `gate_path_ignored "<repo-relative-path>"` in bash gates to skip ignored files.

### Structured output

`gate_fail` / `gate_warn` append to `PYOSSMTOOL_REPORT`:

```json
{
  "findings": [
    {
      "rule_id": "module-size",
      "severity": "error",
      "message": "src/foo.py has 1200 lines (cap 1000)",
      "location": { "file": "src/foo.py", "line": 1 }
    }
  ]
}
```

On failure, pyossmtool normalizes this into `FailureReport` v1 under `reports/failures/`.

### Legacy scripts (no lib)

Existing bash gates that print `FAIL ...` lines still work when registered with `parser: script_text`.

## Catalog entry

```yaml
id: gate.module-size
tool: script
name: Module Size Gate
description: Enforce per-file line limits.
script: .pyossmtool/gates/module-size.sh
parser: gate_json
output_file: .pyossmtool/reports/gate.module-size.json
argv: []
success:
  exit_codes: [0]
```

Optional `argv` entries are passed after the script path; use `{target}` and `{cov}` placeholders.

## Wrapping existing reslab gates

Keep `bin/gates/module-size-check.sh` as-is and register it:

```yaml
id: gate.module-size
tool: script
name: Module Size Gate
script: bin/gates/module-size-check.sh
parser: script_text
argv: []
```

Use `parser: gate_json` after migrating the script to call `gate_fail` / `gate_finish`.
