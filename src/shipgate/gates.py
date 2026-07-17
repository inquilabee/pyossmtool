"""Script gate scaffolding and library path resolution."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from shipgate.constants import PROJECT_CHECKS_DIR, PROJECT_CONFIGS_DIR, PROJECT_GATES_DIR, PROJECT_REPORTS_DIR
from shipgate.registry import BUNDLE_ROOT

GATES_LIB = BUNDLE_ROOT / "defaults" / "gates" / "lib.sh"


def lib_path() -> Path:
    return GATES_LIB


def default_report_path(check_id: str) -> str:
    return f"{PROJECT_REPORTS_DIR}/{check_id}.json"


def gate_check_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"gate.{slug}"


def gate_script_path(name: str, *, python: bool = False) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = ".py" if python else ".sh"
    return f"{PROJECT_GATES_DIR}/{slug}{suffix}"


def gate_catalog_path(name: str) -> Path:
    return Path(PROJECT_CHECKS_DIR) / f"{gate_check_id(name)}.yaml"


def render_gate_script(name: str, description: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"""#!/usr/bin/env bash
# {description}
set -euo pipefail

# shellcheck source=/dev/null
source "$(shipgate gates lib-path)"

gate_init "{slug}"

# Example: fail when a scan root is missing
if [[ ! -d "${{SHIPGATE_TARGET:-.}}" ]]; then
\tgate_fail "missing-target" "Scan target not found: ${{SHIPGATE_TARGET:-.}}"
fi

# Add your policy checks here, e.g.:
# gate_fail "module-size" "src/foo.py exceeds line limit" "src/foo.py" "1"

gate_finish
"""


def render_gate_python_script(name: str, description: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f'''#!/usr/bin/env python3
"""{description}"""
from __future__ import annotations

from shipgate.gate_sdk import Gate

gate = Gate("{slug}")

# Example: fail when scan target is missing
from pathlib import Path

target = Path(gate.target)
if not target.is_dir():
    gate.fail("missing-target", f"Scan target not found: {{target}}")

# Add your policy checks here, e.g.:
# gate.fail("module-size", "src/foo.py exceeds line limit", file="src/foo.py", line=1)

gate.finish()
'''


def render_gate_catalog(name: str, description: str, *, python: bool = False) -> str:
    check_id = gate_check_id(name)
    script = gate_script_path(name, python=python)
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
  project_file: {PROJECT_CONFIGS_DIR}/gates/{check_id}.yaml
success:
  exit_codes: [0]
remediation:
  suggested_commands:
    - "./{script}"
"""


def scaffold_gate(
    project_root: Path,
    name: str,
    description: str,
    *,
    python: bool = False,
) -> tuple[Path, Path]:
    script_rel = gate_script_path(name, python=python)
    script_path = project_root / script_rel
    catalog_path = project_root / gate_catalog_path(name)

    script_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    if script_path.exists():
        raise FileExistsError(f"Gate script already exists: {script_path}")
    if catalog_path.exists():
        raise FileExistsError(f"Gate catalog entry already exists: {catalog_path}")

    script_text = render_gate_python_script(name, description) if python else render_gate_script(name, description)
    script_path.write_text(script_text, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    catalog_path.write_text(render_gate_catalog(name, description, python=python), encoding="utf-8")
    return script_path, catalog_path
