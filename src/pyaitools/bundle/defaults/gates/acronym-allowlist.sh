#!/usr/bin/env bash
# Documented-acronym gate for contributor-facing prose.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyaitools gates lib-path)"

gate_init "acronym-allowlist"

CONFIG="${PYAITOOLS_GATE_CONFIG:?PYAITOOLS_GATE_CONFIG is required}"
ROOT="${PYAITOOLS_ROOT:?PYAITOOLS_ROOT is required}"
REPORT="${PYAITOOLS_REPORT:?PYAITOOLS_REPORT is required}"

"${PYAITOOLS_PYTHON:?PYAITOOLS_PYTHON is required}" -m pyaitools.policy.acronym_allowlist --root "${ROOT}" --config "${CONFIG}" --report "${REPORT}"
exit $?
