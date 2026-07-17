#!/usr/bin/env bash
# Folder breadth gate — caps direct sibling file counts per directory.
set -euo pipefail

# shellcheck source=/dev/null
source "$(shipgate gates lib-path)"

gate_init "folder-breadth"

CONFIG="${SHIPGATE_GATE_CONFIG:?SHIPGATE_GATE_CONFIG is required}"
ROOT="${SHIPGATE_ROOT:?SHIPGATE_ROOT is required}"
REPORT="${SHIPGATE_REPORT:?SHIPGATE_REPORT is required}"

ARGS=(--root "${ROOT}" --config "${CONFIG}" --report "${REPORT}")
if [[ ${GATE_STRICT:-1} == "1" ]]; then
	ARGS+=(--strict)
else
	ARGS+=(--advisory)
fi

"${SHIPGATE_PYTHON:?SHIPGATE_PYTHON is required}" -m shipgate.policy.folder_breadth "${ARGS[@]}"
exit $?
