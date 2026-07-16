#!/usr/bin/env bash
# Folder breadth gate — caps direct sibling file counts per directory.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyossmtool gates lib-path)"

gate_init "folder-breadth"

CONFIG="${PYOSSMTOOL_GATE_CONFIG:?PYOSSMTOOL_GATE_CONFIG is required}"
ROOT="${PYOSSMTOOL_ROOT:?PYOSSMTOOL_ROOT is required}"
REPORT="${PYOSSMTOOL_REPORT:?PYOSSMTOOL_REPORT is required}"

ARGS=(--root "${ROOT}" --config "${CONFIG}" --report "${REPORT}")
if [[ ${GATE_STRICT:-1} == "1" ]]; then
	ARGS+=(--strict)
else
	ARGS+=(--advisory)
fi

"${PYOSSMTOOL_PYTHON:?PYOSSMTOOL_PYTHON is required}" -m pyossmtool.policy.folder_breadth "${ARGS[@]}"
exit $?
