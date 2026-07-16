"""Load gate policy configuration (paths mode > project file > bundled)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pyossmtool.models import CheckDef, ConfigMode, GateConfigSpec, ProjectConfig
from pyossmtool.registry import BUNDLE_ROOT

BUNDLED_CONFIGS = BUNDLE_ROOT / "defaults" / "configs"
BUNDLED_ALLOWLISTS = BUNDLE_ROOT / "defaults" / "allowlists"


def resolve_gate_config_path(
    check: CheckDef,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> Path | None:
    override = _paths_mode_override(check.id, project_root, project_config)
    if override is not None:
        return override

    spec = check.config
    if spec is None:
        return None

    if spec.project_file:
        project_path = project_root / spec.project_file
        if project_path.exists():
            return project_path.resolve()

    return _bundled_config_path(spec)


def load_gate_config(
    check: CheckDef,
    project_root: Path,
    project_config: ProjectConfig | None,
) -> tuple[Path | None, dict[str, Any]]:
    path = resolve_gate_config_path(check, project_root, project_config)
    if path is None or not path.exists():
        return path, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Gate config must be a mapping: {path}")
    config = dict(data)
    _resolve_allowlist_path(check, project_root, config)
    return path, config


def _paths_mode_override(check_id: str, project_root: Path, project_config: ProjectConfig | None) -> Path | None:
    spec = project_config.configs if project_config else None
    if not spec or spec.mode != ConfigMode.PATHS:
        return None
    override = spec.paths.get(check_id)
    return (project_root / override).resolve() if override else None


def _bundled_config_path(spec: GateConfigSpec) -> Path | None:
    if not spec.bundled:
        return None
    path = BUNDLED_CONFIGS / spec.bundled
    return path.resolve() if path.exists() else None


def _resolve_allowlist_path(check: CheckDef, project_root: Path, config: dict[str, Any]) -> None:
    raw = config.get("allowlist_file")
    if not raw:
        return
    path = _allowlist_path(project_root, raw)
    if path.exists():
        config["allowlist_file"] = str(path.resolve())
        return
    bundled = _bundled_allowlist(check)
    config["allowlist_file"] = str(bundled.resolve() if bundled else path.resolve())


def _allowlist_path(project_root: Path, raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return project_root / path


def _bundled_allowlist(check: CheckDef) -> Path | None:
    if check.config is None or not check.config.allowlist_bundled:
        return None
    bundled = BUNDLED_ALLOWLISTS / check.config.allowlist_bundled
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
