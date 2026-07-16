#!/usr/bin/env bash
# Module size gate — portfolio and new-file line caps.
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyaitools gates lib-path)"

gate_init "module-size"

PORTFOLIO_MAX="${GATE_PORTFOLIO_MAX_LINES:-1000}"
NEW_FILE_MAX="${GATE_NEW_FILE_MAX_LINES:-500}"
BASE_BRANCH="${GATE_BASE_BRANCH:-main}"
ALLOWLIST="${GATE_ALLOWLIST_FILE:-}"
IFS=' ' read -r -a SCAN_ROOTS <<<"${GATE_SCAN_ROOTS:-src/}"

count_non_blank_lines() {
	local file="$1"
	grep -cve '^[[:space:]]*$' "${file}" || true
}

is_allowlisted() {
	local rel="$1"
	[[ -n ${ALLOWLIST} && -f ${ALLOWLIST} ]] || return 1
	grep -v '^[[:space:]]*#' "${ALLOWLIST}" | grep -v '^[[:space:]]*$' | grep -Fxq "${rel}"
}

for scan_root in "${SCAN_ROOTS[@]}"; do
	[[ -d ${scan_root} ]] || continue
	while IFS= read -r -d '' file; do
		rel="${file#./}"
		if gate_path_ignored "${rel}"; then
			continue
		fi
		loc="$(count_non_blank_lines "${file}")"
		if ((loc > PORTFOLIO_MAX)) && ! is_allowlisted "${rel}"; then
			gate_fail "module-size" "${rel} has ${loc} lines (portfolio cap ${PORTFOLIO_MAX})" "${rel}" "1"
		fi
	done < <(find "${scan_root}" -name '*.py' -print0)
done

if git rev-parse --verify "${BASE_BRANCH}" >/dev/null 2>&1; then
	MERGE_BASE="$(git merge-base HEAD "${BASE_BRANCH}")"
	new_file_globs=()
	for scan_root in "${SCAN_ROOTS[@]}"; do
		new_file_globs+=("${scan_root}" "${scan_root}/**")
	done
	mapfile -t new_files < <(git diff --name-only --diff-filter=A "${MERGE_BASE}...HEAD" -- "${new_file_globs[@]}" | grep '\.py$' || true)
	for rel in "${new_files[@]}"; do
		[[ -f ${rel} ]] || continue
		if gate_path_ignored "${rel}"; then
			continue
		fi
		loc="$(count_non_blank_lines "${rel}")"
		if ((loc > NEW_FILE_MAX)) && ! is_allowlisted "${rel}"; then
			gate_fail "module-size" "${rel} has ${loc} lines (new-file cap ${NEW_FILE_MAX})" "${rel}" "1"
		fi
	done
fi

gate_finish
