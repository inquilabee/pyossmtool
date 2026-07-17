# shipgate

Quality gates for Python repos that developers can run locally, in CI, or hand to an AI agent without inventing a new workflow each time.

`shipgate` gives you one project config, a bundled catalog of checks, quiet success, and structured failure reports. It is inspired by Trunk and pre-commit, but keeps the surface area small:

```bash
shipgate install
shipgate format
shipgate check
```

## Install

```bash
pip install shipgate
# or
uv add --dev shipgate
```

Requires Python 3.11–3.14.

## 60-Second Setup

Create `shipgate.yaml`:

```yaml
suite: standard
env: managed
target: .
error-format: compact
configs:
  mode: auto
```

Then run:

```bash
shipgate install   # install tools needed by suite
shipgate format    # apply formatter/autofix checks
shipgate check     # report-only quality checks
```

shipgate always respects `.gitignore`; bundled defaults also skip `.venv/`, `.shipgate/`, and `reports/` even when your suite YAML does not list them.

The `suite:` value is the project default. You do not need to repeat `--suite standard`; the CLI reads it from `shipgate.yaml`.

Success is silent and exits `0`. Failures exit `1`, write a JSON report under `reports/failures/`, and print the same report through your configured `error-format`.

## Mental Model

- **Suite**: a named checklist, such as `python-quality`, `standard`, or `all`.
- **Check**: one rule runner inside a suite, such as `ruff.lint` or `ty.check`.
- **`check`**: report-only. It should not rewrite your files.
- **`format`**: applies write/fix checks, such as formatters.
- **`install`**: installs the tools needed by the selected suite.

Most teams pick a suite once in `shipgate.yaml` and run the same three commands everywhere.

## Config That Matters

```yaml
suite: python-quality   # default checklist for install/check/format
env: managed            # managed tools under .shipgate/tools
target: .               # scan root; defaults to .
error-format: compact   # json | log | text | compact | github

configs:
  mode: auto            # repo configs first, bundled fallback
```

Use `--suite` only when you want a one-off override:

```bash
shipgate check --suite extended
shipgate install --suite standard
```

Copy [`shipgate.yaml.example`](shipgate.yaml.example) for an annotated config with ignores, custom checks, gates, and custom error formatters.

## Suites

Suites are bundled starting points. They choose which checks run; tools still discover their own files and `.gitignore` is always respected.

| Suite | Use it for |
| --- | --- |
| `all` | Run every bundled check |
| `all-lint` | Full lint/analysis + tests (no format check or apply) |
| `python-quality` | Core Python lint, format-check, and type checks |
| `formatting` | Report-only formatting drift |
| `format` | Formatter/autofix checks that write files |
| `standard` | Broader portable quality baseline |
| `extended` | Slower optional checks on top of standard |
| `policy` | Bundled script gates |
| `demo` | Internal/sample fixture suite |

Examples:

```yaml
# Local Python repo
suite: python-quality
error-format: text
```

```yaml
# CI baseline with GitHub annotations
suite: standard
error-format: github
```

```yaml
# Max coverage while developing shipgate itself
suite: all
error-format: compact
```

## Error Output

On failure, shipgate always writes the canonical JSON report to disk:

```text
reports/failures/ruff.lint-20260716T163000Z/report.json
```

`error-format` only controls what is printed to stderr.

| Format | Example output |
| --- | --- |
| `json` | Pretty JSON report, including `report_path` |
| `log` | `2026-07-16T12:00:00+00:00 [error] ruff.lint/E501 src/app.py:42: Line too long` |
| `text` | `- [error] E501: Line too long (src/app.py:42)` |
| `compact` | `src/app.py:42: error: E501 Line too long` |
| `github` | `::error file=src/app.py,title=ruff.lint/E501,line=42::Line too long` |

Default is `json` when `error-format` is omitted.

Custom formatters live in `shipgate.yaml`:

```yaml
suite: all
error-format: short
error-formatters:
  short:
    kind: finding_line
    template: "{severity}\t{rule_id}\t{file}:{line}\t{message}"
  jq-summary:
    kind: jq
    program: >
      .findings[] | "[\(.severity)] \(.rule_id) \(.message)"
```

`finding_line` placeholders: `severity`, `rule_id`, `message`, `file`, `line`, `check_id`, `report_path`.

`jq` formatters require `jq` on `PATH`.

## Daily Commands

```bash
shipgate install
shipgate format
shipgate check
```

Inspect what is available:

```bash
shipgate list suites
shipgate list tools
shipgate list checks
```

Run a single check:

```bash
shipgate check --check ruff.lint --target .
```

Export the failure report schema:

```bash
shipgate schema > failure-report.schema.json
```

## Report server

Browse suite runs and findings in a local web UI:

```bash
pip install 'shipgate[server]'
shipgate server
shipgate server --port 8765 --open
```

## Project-Local Gates

Use gates when a repo needs a policy that is not covered by the bundled catalog.

```bash
shipgate gate init module-size --description "Cap module line counts"
```

That creates a shell gate under `.shipgate/gates/` and a catalog entry under `.shipgate/catalog/checks/`. Enable it from `shipgate.yaml`:

```yaml
checks:
  - id: gate.module-size
```

## CI

Minimal GitHub Actions job:

```yaml
name: quality

on:
  pull_request:
  push:
    branches: [main]

jobs:
  shipgate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uvx shipgate install
      - run: uvx shipgate check
```

For GitHub PR annotations, set:

```yaml
error-format: github
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, adding tools/checks, and release notes.

## Bundled tools

| Tool | Purpose |
| --- | --- |
| [Bandit](https://bandit.readthedocs.io/) | Security issue scanner for Python |
| [codespell](https://github.com/codespell-project/codespell) | Common misspellings in text and code |
| [deadcode](https://github.com/alanedwardes/deadcode) | Unused Python code via static analysis |
| [Gitleaks](https://github.com/gitleaks/gitleaks) | Secret scanning for git repositories |
| [Hadolint](https://github.com/hadolint/hadolint) | Dockerfile linter |
| [JSCPD](https://docs.jscpd.io/) | Copy/paste / duplication detector |
| [markdownlint](https://github.com/DavidAnson/markdownlint) | Markdown style linter |
| [mdformat](https://github.com/executablebooks/mdformat) | Markdown formatter |
| [mutmut](https://mutmut.readthedocs.io/) | Mutation testing for Python |
| [pydeps](https://github.com/thebjorn/pydeps) | Python dependency graphs and cycle detection |
| [pytest](https://docs.pytest.org/) | Test runner (optional coverage via pytest-cov) |
| [Radon](https://radon.readthedocs.io/) | Cyclomatic complexity and maintainability metrics |
| [Ruff](https://docs.astral.sh/ruff/) | Fast Python linter and formatter |
| Script gates | Project-local bash policy checks (`shipgate gate init`) |
| [Semgrep](https://semgrep.dev/) | Pattern-based security and quality analysis |
| [ShellCheck](https://www.shellcheck.net/) | Static analysis for shell scripts |
| [shfmt](https://github.com/mvdan/sh) | Shell script formatter |
| [Sourcery](https://sourcery.ai/) | Automated Python review / refactor suggestions |
| [ty](https://docs.astral.sh/ty/) | Astral static type checker for Python |
| [Vulture](https://github.com/jendrikseipp/vulture) | Dead Python code with high confidence |
| [yamlfmt](https://github.com/google/yamlfmt) | YAML formatter |
| [yamllint](https://yamllint.readthedocs.io/) | YAML syntax and style linter |

List the live catalog anytime with `shipgate list tools`.

## License

MIT
