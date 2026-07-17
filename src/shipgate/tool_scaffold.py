"""Scaffold project-local tool catalog entries."""

from __future__ import annotations

import re
from pathlib import Path

from shipgate.constants import PROJECT_CATALOG, PROJECT_CONFIGS_DIR


def tool_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug.replace("-", "_") if slug else "tool"


def check_id_from_tool(tool_id: str) -> str:
    return f"{tool_id}.check"


def render_tool_yaml(tool_id: str, binary: str, files: list[str]) -> str:
    files_yaml = "\n".join(f"  - '{pattern}'" for pattern in files) if files else "  []"
    return f"""id: {tool_id}
name: {tool_id.replace("_", " ").title()}
description: Project-local tool.
install:
  method: skip
binary: {binary}
files:
{files_yaml}
config:
  repo_files:
    - {tool_id}.yaml
  bundled: {tool_id}.yaml
"""


def render_check_yaml(tool_id: str, parser: str = "cli_text") -> str:
    check_id = check_id_from_tool(tool_id)
    binary = tool_id.replace("_", "-")
    return f"""id: {check_id}
tool: {tool_id}
name: {tool_id.replace("_", " ").title()} Check
description: Run {binary} on matched files.
argv:
  - '{{target}}'
parser: {parser}
success:
  exit_codes: [0]
"""


def scaffold_tool(
    project_root: Path,
    name: str,
    *,
    binary: str | None = None,
    files: list[str] | None = None,
    parser: str = "cli_text",
) -> tuple[Path, Path, Path | None]:
    tool_id = tool_id_from_name(name)
    tool_binary = binary or tool_id.replace("_", "-")
    file_globs = files or ["**/*"]
    catalog_root = project_root / PROJECT_CATALOG
    tools_dir = catalog_root / "tools"
    checks_dir = catalog_root / "checks"
    configs_dir = project_root / PROJECT_CONFIGS_DIR
    tools_dir.mkdir(parents=True, exist_ok=True)
    checks_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)

    tool_path = tools_dir / f"{tool_id}.yaml"
    check_path = checks_dir / f"{check_id_from_tool(tool_id)}.yaml"
    config_path = configs_dir / f"{tool_id}.yaml"

    if tool_path.exists():
        raise FileExistsError(f"Tool catalog entry already exists: {tool_path}")
    if check_path.exists():
        raise FileExistsError(f"Check catalog entry already exists: {check_path}")

    tool_path.write_text(render_tool_yaml(tool_id, tool_binary, file_globs), encoding="utf-8")
    check_path.write_text(render_check_yaml(tool_id, parser=parser), encoding="utf-8")
    if not config_path.exists():
        config_path.write_text(f"# Optional config for {tool_id}\n", encoding="utf-8")
        return tool_path, check_path, config_path
    return tool_path, check_path, None
