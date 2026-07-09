#!/usr/bin/env bash
# pyaitools script-gate helper library.
# Source from project gates: source "$(pyaitools gates lib-path)"
set -euo pipefail

gate_init() {
	GATE_NAME="${1:-script-gate}"
	GATE_FINDING_COUNT=0
	if [[ -z "${PYAITOOLS_REPORT:-}" ]]; then
		echo "gate_init: PYAITOOLS_REPORT is not set (pyaitools runner should set this)" >&2
		exit 2
	fi
	mkdir -p "$(dirname "${PYAITOOLS_REPORT}")"
	printf '%s\n' '{"findings":[]}' >"${PYAITOOLS_REPORT}"
}

_gate_append_finding() {
	local rule_id="$1"
	local severity="$2"
	local message="$3"
	local file="${4:-}"
	local line="${5:-}"
	python3 - "${PYAITOOLS_REPORT}" "${rule_id}" "${severity}" "${message}" "${file}" "${line}" <<'PY'
import json
import sys
from pathlib import Path

report_path, rule_id, severity, message, file, line = sys.argv[1:7]
payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
finding = {
    "rule_id": rule_id,
    "severity": severity,
    "message": message,
}
if file:
    location = {"file": file}
    if line:
        try:
            location["line"] = int(line)
        except ValueError:
            pass
    finding["location"] = location
payload.setdefault("findings", []).append(finding)
Path(report_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
	GATE_FINDING_COUNT=$((GATE_FINDING_COUNT + 1))
}

gate_fail() {
	local rule_id="${1:-gate}"
	local message="${2:-gate failed}"
	local file="${3:-}"
	local line="${4:-}"
	_gate_append_finding "${rule_id}" "error" "${message}" "${file}" "${line}"
	echo "FAIL ${rule_id}: ${message}" >&2
}

gate_warn() {
	local rule_id="${1:-gate}"
	local message="${2:-gate warning}"
	local file="${3:-}"
	local line="${4:-}"
	_gate_append_finding "${rule_id}" "warning" "${message}" "${file}" "${line}"
	echo "WARN ${rule_id}: ${message}" >&2
}

gate_finish() {
	if ((GATE_FINDING_COUNT > 0)); then
		echo "gate '${GATE_NAME}' failed with ${GATE_FINDING_COUNT} finding(s)" >&2
		exit 1
	fi
	exit 0
}
