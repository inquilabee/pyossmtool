#!/usr/bin/env bash
# pyossmtool script-gate helper library.
# Source from project gates: source "$(pyossmtool gates lib-path)"
set -euo pipefail

gate_init() {
	GATE_NAME="${1:-script-gate}"
	GATE_FINDING_COUNT=0
	if [[ -z "${PYOSSMTOOL_REPORT:-}" ]]; then
		echo "gate_init: PYOSSMTOOL_REPORT is not set (pyossmtool runner should set this)" >&2
		exit 2
	fi
	mkdir -p "$(dirname "${PYOSSMTOOL_REPORT}")"
	printf '%s\n' '{"findings":[]}' >"${PYOSSMTOOL_REPORT}"
}

_gate_append_finding() {
	local rule_id="$1"
	local severity="$2"
	local message="$3"
	local file="${4:-}"
	local line="${5:-}"
	python3 - "${PYOSSMTOOL_REPORT}" "${rule_id}" "${severity}" "${message}" "${file}" "${line}" <<'PY'
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

gate_path_ignored() {
	local rel_path="${1#./}"
	"${PYOSSMTOOL_PYTHON:-python3}" - "${rel_path}" <<'PY'
import fnmatch
import os
import sys
from pathlib import Path

try:
    import pathspec
except ImportError:
    pathspec = None

rel = sys.argv[1].replace("\\", "/").lstrip("./")
patterns: list[str] = [
    p.strip() for p in os.environ.get("PYOSSMTOOL_IGNORE_PATHS", "").splitlines() if p.strip()
]
for profile in os.environ.get("PYOSSMTOOL_IGNORE_PROFILES", "").splitlines():
    path = Path(profile.strip())
    if not path.is_file():
        continue
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("!"):
            patterns.append(stripped)

if not patterns:
    raise SystemExit(1)

if pathspec is not None:
    matcher = pathspec.PathSpec.from_lines("gitignore", patterns)
    raise SystemExit(0 if matcher.match_file(rel) else 1)

for pattern in patterns:
    normalized = pattern.rstrip("/")
    if rel == normalized or rel.startswith(f"{normalized}/"):
        raise SystemExit(0)
    if "*" in pattern and fnmatch.fnmatch(rel, pattern):
        raise SystemExit(0)
raise SystemExit(1)
PY
}

gate_finish() {
	if ((GATE_FINDING_COUNT > 0)); then
		echo "gate '${GATE_NAME}' failed with ${GATE_FINDING_COUNT} finding(s)" >&2
		exit 1
	fi
	exit 0
}
