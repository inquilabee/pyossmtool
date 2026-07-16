#!/usr/bin/env bash
# Folder breadth gate — caps direct sibling file counts per directory.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyaitools gates lib-path)"

gate_init "folder-breadth"

CONFIG="${PYAITOOLS_GATE_CONFIG:?PYAITOOLS_GATE_CONFIG is required}"
ROOT="${PYAITOOLS_ROOT:?PYAITOOLS_ROOT is required}"
REPORT="${PYAITOOLS_REPORT:?PYAITOOLS_REPORT is required}"

ARGS=(--root "${ROOT}" --config "${CONFIG}" --report "${REPORT}")
if [[ ${GATE_STRICT:-1} == "1" ]]; then
	ARGS+=(--strict)
else
	ARGS+=(--advisory)
fi

"${PYAITOOLS_PYTHON:?PYAITOOLS_PYTHON is required}" -m pyaitools.policy.folder_breadth "${ARGS[@]}"
exit $?
