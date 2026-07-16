#!/usr/bin/env bash
# Module private-vars gate — no leading-underscore module-level names.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyaitools gates lib-path)"

gate_init "module-private-vars"

BASE_BRANCH="${GATE_BASE_BRANCH:-main}"
ALLOWLIST="${GATE_ALLOWLIST_FILE:-}"
IFS=' ' read -r -a SCAN_ROOTS <<<"${GATE_SCAN_ROOTS:-src/}"

ASSIGN_PATTERN='^_[^_][A-Za-z0-9_]*[[:space:]]*[:=]'
DEF_PATTERN='^(async[[:space:]]+)?def[[:space:]]+_[^_][A-Za-z0-9_]*[[:space:]]*[\(:]'
CLASS_PATTERN='^class[[:space:]]+_[^_][A-Za-z0-9_]*[[:space:]]*[\(:]'

is_allowlisted() {
	local rel="$1"
	[[ -n ${ALLOWLIST} && -f ${ALLOWLIST} ]] || return 1
	grep -v '^[[:space:]]*#' "${ALLOWLIST}" | grep -v '^[[:space:]]*$' | grep -Fxq "${rel}"
}

is_strict_file() {
	local rel="$1"
	local strict
	for strict in "${STRICT_FILES[@]-}"; do
		[[ ${rel} == "${strict}" ]] && return 0
	done
	return 1
}

report_matches() {
	local rel="$1"
	local label="$2"
	local matches="$3"
	if [[ -n ${matches} ]]; then
		while IFS= read -r line; do
			[[ -n ${line} ]] || continue
			line_no="${line%%:*}"
			gate_fail "private-${label}" "${rel}:${line}" "${rel}" "${line_no}"
		done <<<"${matches}"
	fi
}

STRICT_FILES=()
if git rev-parse --verify "${BASE_BRANCH}" >/dev/null 2>&1; then
	MERGE_BASE="$(git merge-base HEAD "${BASE_BRANCH}")"
	new_file_globs=()
	for scan_root in "${SCAN_ROOTS[@]}"; do
		new_file_globs+=("${scan_root}" "${scan_root}/**")
	done
	mapfile -t STRICT_FILES < <(git diff --name-only --diff-filter=A "${MERGE_BASE}...HEAD" -- "${new_file_globs[@]}" | grep '\.py$' || true)
fi

for scan_dir in "${SCAN_ROOTS[@]}"; do
	[[ -d ${scan_dir} ]] || continue
	while IFS= read -r -d '' file; do
		rel="${file#./}"
		if gate_path_ignored "${rel}"; then
			continue
		fi
		if is_allowlisted "${rel}"; then
			continue
		fi
		assign_matches="$(grep -nE "${ASSIGN_PATTERN}" "${file}" || true)"
		report_matches "${rel}" "assignment" "${assign_matches}"
		if is_strict_file "${rel}"; then
			def_matches="$(grep -nE "${DEF_PATTERN}" "${file}" || true)"
			class_matches="$(grep -nE "${CLASS_PATTERN}" "${file}" || true)"
			report_matches "${rel}" "function" "${def_matches}"
			report_matches "${rel}" "class" "${class_matches}"
		fi
	done < <(find "${scan_dir}" -name '*.py' -print0)
done

gate_finish
