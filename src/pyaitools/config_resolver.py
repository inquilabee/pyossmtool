"""Resolve tool configuration: repo-native > pyaitools.yaml paths > bundled defaults."""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from pyaitools.models import ConfigMode, ConfigSpec, ProjectConfig
from pyaitools.registry import PACKAGE_ROOT

DEFAULTS_DIR = PACKAGE_ROOT / "defaults" / "configs"

_REPO_CONFIG_FILENAMES: dict[str, tuple[str, ...]] = {
    "yamlfmt": (".yamlfmt.yaml", ".yamlfmt.yml", "yamlfmt.yaml"),
    "yamllint": (".yamllint", ".yamllint.yaml", ".yamllint.yml"),
    "markdownlint": (".markdownlint.json", ".markdownlint.yaml", ".markdownlint.yml"),
}


_CONFIG_ARGV_FLAG: dict[str, str] = {
    "ruff": "--config",
    "ty": "--config",
    "yamlfmt": "-conf",
    "semgrep": "--config",
    "yamllint": "-c",
    "markdownlint": "-c",
    "bandit": "-c",
}

_NAMED_CONFIG_TOOLS = frozenset({"yamlfmt", "yamllint", "markdownlint"})

RepoConfigChecker = Callable[..., bool]


class ConfigResolver:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.defaults_dir = DEFAULTS_DIR

    def extra_argv(self, tool_id: str, project_config: ProjectConfig | None) -> list[str]:
        config_path = self._selected_config_path(tool_id, project_config)
        if config_path is None:
            return []
        return self._config_argv(tool_id, config_path)

    def resolve_config_path(
        self, tool_id: str, project_config: ProjectConfig | None
    ) -> Path | None:
        path = self._selected_config_path(tool_id, project_config)
        return path.resolve() if path and path.exists() else None

    def _selected_config_path(
        self, tool_id: str, project_config: ProjectConfig | None
    ) -> Path | None:
        spec = project_config.configs if project_config else ConfigSpec()
        if spec.mode == ConfigMode.PATHS:
            return self._paths_mode_config(tool_id, spec)
        if spec.mode == ConfigMode.BUNDLED:
            return self._bundled_mode_config(tool_id)
        return self._auto_mode_config(tool_id)

    def _paths_mode_config(self, tool_id: str, spec: ConfigSpec) -> Path | None:
        path = spec.paths.get(tool_id)
        return (self.project_root / path).resolve() if path else None

    def _bundled_mode_config(self, tool_id: str) -> Path | None:
        bundled = self._bundled_path(tool_id)
        return bundled.resolve() if bundled and bundled.exists() else None

    def _auto_mode_config(self, tool_id: str) -> Path | None:
        if tool_id == "bandit" and self._pyproject_has_table("tool", "bandit"):
            return self.project_root / "pyproject.toml"
        if self._repo_has_config(tool_id):
            return None
        return self._bundled_mode_config(tool_id)

    def _config_argv(self, tool_id: str, config_path: Path) -> list[str]:
        if not config_path.exists() or tool_id in {"semgrep", "markdownlint"}:
            return []
        flag = _CONFIG_ARGV_FLAG.get(tool_id)
        return [flag, str(config_path)] if flag else []

    def _repo_has_config(self, tool_id: str) -> bool:
        if tool_id == "bandit":
            return False
        checkers = self._repo_config_checkers()
        checker = checkers.get(tool_id)
        if checker is None:
            return False
        if tool_id in _NAMED_CONFIG_TOOLS:
            return checker(tool_id)
        return checker()

    def _repo_config_checkers(self) -> dict[str, RepoConfigChecker]:
        return {
            "ruff": self._repo_has_ruff_config,
            "ty": self._repo_has_ty_config,
            "mdformat": self._repo_has_mdformat_config,
            "yamlfmt": self._repo_has_named_config_files,
            "shfmt": self._repo_has_editorconfig,
            "semgrep": self._repo_has_semgrep_config,
            "yamllint": self._repo_has_named_config_files,
            "markdownlint": self._repo_has_named_config_files,
            "codespell": self._repo_has_codespell_config,
        }

    def _bundled_path(self, tool_id: str) -> Path | None:
        mapping = {
            "ruff": self.defaults_dir / "ruff.toml",
            "ty": self.defaults_dir / "ty.toml",
            "yamlfmt": self.defaults_dir / "yamlfmt.yaml",
            "yamllint": self.defaults_dir / "yamllint.yaml",
            "markdownlint": self.defaults_dir / "markdownlint.json",
            "bandit": self.defaults_dir / "bandit.yaml",
            "semgrep": PACKAGE_ROOT / "defaults" / "semgrep" / "python-quality.yml",
        }
        path = mapping.get(tool_id)
        return path if path and path.exists() else None

    def _repo_has_ruff_config(self) -> bool:
        if (self.project_root / "ruff.toml").exists():
            return True
        return self._pyproject_has_table("tool", "ruff")

    def _repo_has_ty_config(self) -> bool:
        return self._pyproject_has_table("tool", "ty")

    def _repo_has_mdformat_config(self) -> bool:
        return (self.project_root / ".mdformat.toml").exists()

    def _repo_has_named_config_files(self, tool_id: str) -> bool:
        for name in _REPO_CONFIG_FILENAMES[tool_id]:
            if (self.project_root / name).exists():
                return True
        return False

    def _repo_has_editorconfig(self) -> bool:
        return (self.project_root / ".editorconfig").exists()

    def _repo_has_semgrep_config(self) -> bool:
        for candidate in (
            self.project_root / ".semgrep",
            self.project_root / ".tools" / "semgrep",
        ):
            if candidate.is_dir() and any(candidate.iterdir()):
                return True
        return False

    def _repo_has_codespell_config(self) -> bool:
        return self._pyproject_has_table("tool", "codespell")

    def _pyproject_has_table(self, *keys: str) -> bool:
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
