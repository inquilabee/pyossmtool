#!/usr/bin/env bash
# Documented-acronym gate for contributor-facing prose.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyossmtool gates lib-path)"

gate_init "acronym-allowlist"

CONFIG="${PYOSSMTOOL_GATE_CONFIG:?PYOSSMTOOL_GATE_CONFIG is required}"
ROOT="${PYOSSMTOOL_ROOT:?PYOSSMTOOL_ROOT is required}"
REPORT="${PYOSSMTOOL_REPORT:?PYOSSMTOOL_REPORT is required}"

"${PYOSSMTOOL_PYTHON:?PYOSSMTOOL_PYTHON is required}" -m pyossmtool.policy.acronym_allowlist --root "${ROOT}" --config "${CONFIG}" --report "${REPORT}"
exit $?
