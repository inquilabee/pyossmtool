"""Resolve tool configuration: repo-native > pyaitools.yaml paths > bundled defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pyaitools.models import (
    ConfigMode,
    ConfigSpec,
    ProjectConfig,
    ToolConfigSpec,
    ToolDef,
)
from pyaitools.registry import BUNDLE_ROOT

DEFAULTS_DIR = BUNDLE_ROOT / "defaults" / "configs"


class ConfigResolver:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.defaults_dir = DEFAULTS_DIR

    def extra_argv(self, tool: ToolDef, project_config: ProjectConfig | None) -> list[str]:
        config_path = self._selected_config_path(tool, project_config)
        if config_path is None:
            return []
        return self._config_argv(tool, config_path)

    def resolve_config_path(self, tool: ToolDef, project_config: ProjectConfig | None) -> Path | None:
        path = self._selected_config_path(tool, project_config)
        return path.resolve() if path and path.exists() else None

    def _selected_config_path(self, tool: ToolDef, project_config: ProjectConfig | None) -> Path | None:
        spec = project_config.configs if project_config else ConfigSpec()
        if spec.mode == ConfigMode.PATHS:
            return self._paths_mode_config(tool.id, spec)
        if tool.config is None:
            return None
        if spec.mode == ConfigMode.BUNDLED:
            return self._bundled_mode_config(tool.config)
        return self._auto_mode_config(tool.config)

    def _paths_mode_config(self, tool_id: str, spec: ConfigSpec) -> Path | None:
        path = spec.paths.get(tool_id)
        return (self.project_root / path).resolve() if path else None

    def _bundled_mode_config(self, config: ToolConfigSpec) -> Path | None:
        bundled = self._bundled_path(config)
        return bundled.resolve() if bundled and bundled.exists() else None

    def _auto_mode_config(self, config: ToolConfigSpec) -> Path | None:
        if config.use_pyproject_as_path and self._pyproject_has_table(*config.pyproject):
            return self.project_root / "pyproject.toml"
        if self._repo_has_config(config):
            return None
        return self._bundled_mode_config(config)

    def _config_argv(self, tool: ToolDef, config_path: Path) -> list[str]:
        if not config_path.exists() or tool.config is None:
            return []
        if not tool.config.should_pass_flag() or not tool.config.flag:
            return []
        return [tool.config.flag, str(config_path)]

    def _repo_has_config(self, config: ToolConfigSpec) -> bool:
        if self._repo_has_files(config):
            return True
        if self._repo_has_dirs(config):
            return True
        return bool(config.pyproject) and self._pyproject_has_table(*config.pyproject)

    def _repo_has_files(self, config: ToolConfigSpec) -> bool:
        return any((self.project_root / name).exists() for name in config.repo_files)

    def _repo_has_dirs(self, config: ToolConfigSpec) -> bool:
        return any(self._nonempty_dir(name) for name in config.repo_dirs)

    def _nonempty_dir(self, rel: str) -> bool:
        candidate = self.project_root / rel
        return candidate.is_dir() and any(candidate.iterdir())

    def _bundled_path(self, config: ToolConfigSpec) -> Path | None:
        if config.bundled_path:
            path = BUNDLE_ROOT / config.bundled_path
            return path if path.exists() else None
        if config.bundled:
            path = self.defaults_dir / config.bundled
            return path if path.exists() else None
        return None

    def _pyproject_has_table(self, *keys: str) -> bool:
        if not keys:
            return False
        data = self._load_pyproject()
        if data is None:
            return False
        return _dict_has_path(data, keys)

    def _load_pyproject(self) -> dict | None:
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists():
            return None
        try:
            return tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return None


def _dict_has_path(data: dict, keys: tuple[str, ...]) -> bool:
    node: object = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True
