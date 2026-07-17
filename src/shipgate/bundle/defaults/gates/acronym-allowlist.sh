#!/usr/bin/env bash
# Documented-acronym gate for contributor-facing prose.
set -euo pipefail

# shellcheck source=/dev/null
source "$(shipgate gates lib-path)"

gate_init "acronym-allowlist"

CONFIG="${SHIPGATE_GATE_CONFIG:?SHIPGATE_GATE_CONFIG is required}"
ROOT="${SHIPGATE_ROOT:?SHIPGATE_ROOT is required}"
REPORT="${SHIPGATE_REPORT:?SHIPGATE_REPORT is required}"

"${SHIPGATE_PYTHON:?SHIPGATE_PYTHON is required}" -m shipgate.policy.acronym_allowlist --root "${ROOT}" --config "${CONFIG}" --report "${REPORT}"
exit $?
