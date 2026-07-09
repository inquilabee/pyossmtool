"""Load gate policy configuration (repo > pyaitools.yaml paths > bundled)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pyaitools.models import ConfigMode, ProjectConfig
from pyaitools.registry import PACKAGE_ROOT

BUNDLED_GATES_CONFIG = PACKAGE_ROOT / "defaults" / "configs" / "gates"
BUNDLED_ALLOWLISTS = PACKAGE_ROOT / "defaults" / "allowlists"

GATE_ALLOWLIST_FILES = {
    "gate.module-size": "module-size.txt",
    "gate.module-private-vars": "module-private-vars.txt",
    "gate.folder-breadth": "folder-breadth.txt",
    "gate.acronym-allowlist": "acronyms.yaml",
}


def gate_config_stem(check_id: str) -> str:
    return check_id.removeprefix("gate.")


def resolve_gate_config_path(
    check_id: str,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> Path:
    spec = project_config.configs if project_config else None
    if spec and spec.mode == ConfigMode.PATHS:
        override = spec.paths.get(check_id)
        if override:
            return (project_root / override).resolve()

    project_path = project_root / ".pyaitools" / "configs" / "gates" / f"{check_id}.yaml"
    if project_path.exists():
        return project_path.resolve()

    # Reslab-style legacy paths
    legacy_names = {
        "gate.module-size": project_root / ".tools" / "module-size-config.yaml",
        "gate.module-private-vars": project_root / ".tools" / "module-private-vars-config.yaml",
        "gate.folder-breadth": project_root / ".tools" / "folder-breadth-config.env",
        "gate.acronym-allowlist": project_root / ".tools" / "acronym-allowlist-config.yaml",
    }
    legacy = legacy_names.get(check_id)
    if legacy and legacy.exists():
        return legacy.resolve()

    bundled = BUNDLED_GATES_CONFIG / f"{gate_config_stem(check_id)}.yaml"
    return bundled.resolve()


def load_gate_config(
    check_id: str,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_gate_config_path(check_id, project_root, project_config)
    if not path.exists():
        bundled = BUNDLED_GATES_CONFIG / f"{gate_config_stem(check_id)}.yaml"
        if bundled.exists():
            path = bundled.resolve()
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            return path, {}
    elif path.suffix == ".env":
        return path, _load_env_file(path)
    else:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if not isinstance(data, dict):
        msg = f"Gate config must be a mapping: {path}"
        raise ValueError(msg)

    data = dict(data)
    _resolve_allowlist_path(check_id, project_root, data)
    return path, data


def _resolve_allowlist_path(check_id: str, project_root: Path, config: dict[str, Any]) -> None:
    raw = config.get("allowlist_file")
    if not raw:
        return
    path = Path(str(raw))
    if not path.is_absolute():
        path = project_root / path
    if path.exists():
        config["allowlist_file"] = str(path.resolve())
        return
    bundled_name = GATE_ALLOWLIST_FILES.get(check_id)
    if bundled_name:
        bundled = BUNDLED_ALLOWLISTS / bundled_name
        if bundled.exists():
            config["allowlist_file"] = str(bundled.resolve())
            return
    config["allowlist_file"] = str(path.resolve())


def gate_env_from_config(config: dict[str, Any], project_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in config.items():
        env_key = f"GATE_{key.upper()}"
        if isinstance(value, list):
            env[env_key] = " ".join(str(item) for item in value)
        elif isinstance(value, bool):
            env[env_key] = "1" if value else "0"
        elif value is not None:
            env[env_key] = str(value)
    if "allowlist_file" in config and config["allowlist_file"]:
        allowlist = Path(str(config["allowlist_file"]))
        if not allowlist.is_absolute():
            allowlist = project_root / allowlist
        env["GATE_ALLOWLIST_FILE"] = str(allowlist.resolve())
    return env


def _load_env_file(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        normalized = key.strip().lower()
        if normalized == "folder_breadth_max":
            values["max_allowed"] = int(value.strip())
        elif normalized == "folder_breadth_scan_roots":
            values["scan_roots"] = [part.strip() for part in value.strip().split(",") if part.strip()]
        elif normalized == "folder_breadth_extensions":
            values["extensions"] = [part.strip() for part in value.strip().split(",") if part.strip()]
        else:
            values[normalized] = value.strip()
    return values
