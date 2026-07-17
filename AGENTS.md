# Agent Guide

shipgate is a portable quality-gate orchestrator (inspired by Trunk and pre-commit) for Python-first repositories with opinionated defaults and little required configuration.

## Tool Guide

### Check Issues (report-only)

```bash
shipgate check
```

### Format / Fix Issues (writes)

```bash
shipgate format
```

## Principles

- Tools should be easy to add with little to no configuration.
- Running tools should follow a similar API (`check` / `format`).
- A tool is silent on success and emits AI- and human-consumable structured errors on failure.
- **Framework code quality is a product feature.** Clarity, typing, tests, and small modules are non-negotiable — the orchestrator that improves code quality must itself meet that bar.
