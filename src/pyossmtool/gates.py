"""Script gate scaffolding and library path resolution."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from pyossmtool.registry import BUNDLE_ROOT

GATES_LIB = BUNDLE_ROOT / "defaults" / "gates" / "lib.sh"
PROJECT_GATES_DIR = ".pyossmtool/gates"
PROJECT_CHECKS_DIR = ".pyossmtool/catalog/checks"


def lib_path() -> Path:
    return GATES_LIB


def default_report_path(check_id: str) -> str:
    return f".pyossmtool/reports/{check_id}.json"


def gate_check_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"gate.{slug}"


def gate_script_path(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{PROJECT_GATES_DIR}/{slug}.sh"


def gate_catalog_path(name: str) -> Path:
    return Path(PROJECT_CHECKS_DIR) / f"{gate_check_id(name)}.yaml"


def render_gate_script(name: str, description: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"""#!/usr/bin/env bash
# {description}
set -euo pipefail

# shellcheck source=/dev/null
source "$(pyossmtool gates lib-path)"

gate_init "{slug}"

# Example: fail when a scan root is missing
if [[ ! -d "${{PYOSSMTOOL_TARGET:-.}}" ]]; then
\tgate_fail "missing-target" "Scan target not found: ${{PYOSSMTOOL_TARGET:-.}}"
fi

# Add your policy checks here, e.g.:
# gate_fail "module-size" "src/foo.py exceeds line limit" "src/foo.py" "1"

gate_finish
"""


def render_gate_catalog(name: str, description: str) -> str:
    check_id = gate_check_id(name)
    script = gate_script_path(name)
    report = default_report_path(check_id)
    title = name.replace("-", " ").title()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"""id: {check_id}
tool: script
name: {title}
description: {description}
script: {script}
parser: gate_json
output_file: {report}
argv: []
config:
  bundled: gates/{slug}.yaml
  project_file: .pyossmtool/configs/gates/{check_id}.yaml
success:
  exit_codes: [0]
remediation:
  suggested_commands:
    - "./{script}"
"""


def scaffold_gate(project_root: Path, name: str, description: str) -> tuple[Path, Path]:
    script_rel = gate_script_path(name)
    script_path = project_root / script_rel
    catalog_path = project_root / gate_catalog_path(name)

    script_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    if script_path.exists():
        raise FileExistsError(f"Gate script already exists: {script_path}")
    if catalog_path.exists():
        raise FileExistsError(f"Gate catalog entry already exists: {catalog_path}")

    script_path.write_text(render_gate_script(name, description), encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    catalog_path.write_text(render_gate_catalog(name, description), encoding="utf-8")
    return script_path, catalog_path
