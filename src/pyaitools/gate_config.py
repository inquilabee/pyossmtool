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


_LEGACY_GATE_PATHS: dict[str, str] = {
    "gate.module-size": ".tools/module-size-config.yaml",
    "gate.module-private-vars": ".tools/module-private-vars-config.yaml",
    "gate.folder-breadth": ".tools/folder-breadth-config.env",
    "gate.acronym-allowlist": ".tools/acronym-allowlist-config.yaml",
}


def resolve_gate_config_path(
    check_id: str,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> Path:
    override = _paths_mode_gate_override(check_id, project_root, project_config)
    if override is not None:
        return override

    project_path = project_root / ".pyaitools" / "configs" / "gates" / f"{check_id}.yaml"
    if project_path.exists():
        return project_path.resolve()

    legacy = _legacy_gate_config(project_root, check_id)
    if legacy is not None:
        return legacy

    return (BUNDLED_GATES_CONFIG / f"{gate_config_stem(check_id)}.yaml").resolve()


def _paths_mode_gate_override(
    check_id: str, project_root: Path, project_config: ProjectConfig | None
) -> Path | None:
    spec = project_config.configs if project_config else None
    if not spec or spec.mode != ConfigMode.PATHS:
        return None
    override = spec.paths.get(check_id)
    return (project_root / override).resolve() if override else None


def _legacy_gate_config(project_root: Path, check_id: str) -> Path | None:
    rel = _LEGACY_GATE_PATHS.get(check_id)
    if not rel:
        return None
    path = project_root / rel
    return path.resolve() if path.exists() else None


def load_gate_config(
    check_id: str,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> tuple[Path, dict[str, Any]]:
    path = resolve_gate_config_path(check_id, project_root, project_config)
    data = _read_gate_config_data(path, check_id)
    if not data:
        return path, {}
    if not isinstance(data, dict):
        msg = f"Gate config must be a mapping: {path}"
        raise ValueError(msg)
    config = dict(data)
    _resolve_allowlist_path(check_id, project_root, config)
    return path, config


def _read_gate_config_data(path: Path, check_id: str) -> dict[str, Any] | list | None:
    if not path.exists():
        bundled = BUNDLED_GATES_CONFIG / f"{gate_config_stem(check_id)}.yaml"
        if not bundled.exists():
            return None
        path = bundled.resolve()
    if path.suffix == ".env":
        return _load_env_file(path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _resolve_allowlist_path(check_id: str, project_root: Path, config: dict[str, Any]) -> None:
    raw = config.get("allowlist_file")
    if not raw:
        return
    path = _allowlist_path(project_root, raw)
    if path.exists():
        config["allowlist_file"] = str(path.resolve())
        return
    bundled = _bundled_allowlist(check_id)
    config["allowlist_file"] = str(bundled.resolve() if bundled else path.resolve())


def _allowlist_path(project_root: Path, raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return project_root / path


def _bundled_allowlist(check_id: str) -> Path | None:
    bundled_name = GATE_ALLOWLIST_FILES.get(check_id)
    if not bundled_name:
        return None
    bundled = BUNDLED_ALLOWLISTS / bundled_name
    return bundled if bundled.exists() else None


def gate_env_from_config(config: dict[str, Any], project_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in config.items():
        if value is None:
            continue
        env[f"GATE_{key.upper()}"] = _gate_env_value(value)
    allowlist = config.get("allowlist_file")
    if allowlist:
        env["GATE_ALLOWLIST_FILE"] = str(_allowlist_env_path(allowlist, project_root))
    return env


def _allowlist_env_path(allowlist: Any, project_root: Path) -> Path:
    path = Path(str(allowlist))
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _gate_env_value(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _load_env_file(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_env_line(line)
        if key is None or value is None:
            continue
        values.update(_map_env_key(key, value))
    return values


def _parse_env_line(line: str) -> tuple[str | None, str | None]:
    stripped = line.split("#", 1)[0].strip()
    if not stripped or "=" not in stripped:
        return None, None
    key, value = stripped.split("=", 1)
    return key.strip().lower(), value.strip()


def _map_env_key(key: str, value: str) -> dict[str, Any]:
    if key == "folder_breadth_max":
        return {"max_allowed": int(value)}
    if key == "folder_breadth_scan_roots":
        return {"scan_roots": _split_csv(value)}
    if key == "folder_breadth_extensions":
        return {"extensions": _split_csv(value)}
    return {key: value}


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
