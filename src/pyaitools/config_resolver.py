"""Resolve tool configuration: repo-native > pyaitools.yaml paths > bundled defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pyaitools.models import ConfigMode, ConfigSpec, ProjectConfig
from pyaitools.registry import PACKAGE_ROOT

DEFAULTS_DIR = PACKAGE_ROOT / "defaults" / "configs"


class ConfigResolver:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.defaults_dir = DEFAULTS_DIR

    def extra_argv(self, tool_id: str, project_config: ProjectConfig | None) -> list[str]:
        spec = project_config.configs if project_config else ConfigSpec()
        if spec.mode == ConfigMode.PATHS:
            path = spec.paths.get(tool_id)
            if path:
                return self._config_argv(tool_id, self.project_root / path)
            return []

        if spec.mode == ConfigMode.BUNDLED:
            bundled = self._bundled_path(tool_id)
            return self._config_argv(tool_id, bundled) if bundled else []

        # auto: repo-native discovery wins (no flags); else bundled fallback
        if self._repo_has_config(tool_id):
            return []
        bundled = self._bundled_path(tool_id)
        return self._config_argv(tool_id, bundled) if bundled else []

    def _config_argv(self, tool_id: str, config_path: Path) -> list[str]:
        if not config_path.exists():
            return []
        if tool_id == "ruff":
            return ["--config", str(config_path)]
        if tool_id == "ty":
            return ["--config", str(config_path)]
        if tool_id == "yamlfmt":
            return ["-conf", str(config_path)]
        if tool_id == "semgrep":
            return ["--config", str(config_path)]
        if tool_id == "yamllint":
            return ["-c", str(config_path)]
        if tool_id == "markdownlint":
            return ["--config", str(config_path)]
        return []

    def _bundled_path(self, tool_id: str) -> Path | None:
        mapping = {
            "ruff": self.defaults_dir / "ruff.toml",
            "ty": self.defaults_dir / "ty.toml",
            "yamlfmt": self.defaults_dir / "yamlfmt.yaml",
            "yamllint": self.defaults_dir / "yamllint.yaml",
            "markdownlint": self.defaults_dir / "markdownlint.json",
            "semgrep": PACKAGE_ROOT / "defaults" / "semgrep" / "python-quality.yml",
        }
        path = mapping.get(tool_id)
        return path if path and path.exists() else None

    def _repo_has_config(self, tool_id: str) -> bool:
        if tool_id == "ruff":
            if (self.project_root / "ruff.toml").exists():
                return True
            return self._pyproject_has_table("tool", "ruff")
        if tool_id == "ty":
            return self._pyproject_has_table("tool", "ty")
        if tool_id == "mdformat":
            return (self.project_root / ".mdformat.toml").exists()
        if tool_id == "yamlfmt":
            for name in (".yamlfmt.yaml", ".yamlfmt.yml", "yamlfmt.yaml"):
                if (self.project_root / name).exists():
                    return True
            return False
        if tool_id == "shfmt":
            return (self.project_root / ".editorconfig").exists()
        if tool_id == "semgrep":
            for candidate in (
                self.project_root / ".semgrep",
                self.project_root / ".tools" / "semgrep",
            ):
                if candidate.is_dir() and any(candidate.iterdir()):
                    return True
            return False
        if tool_id == "yamllint":
            for name in (".yamllint", ".yamllint.yaml", ".yamllint.yml"):
                if (self.project_root / name).exists():
                    return True
            return False
        if tool_id == "markdownlint":
            for name in (".markdownlint.json", ".markdownlint.yaml", ".markdownlint.yml"):
                if (self.project_root / name).exists():
                    return True
            return False
        if tool_id == "codespell":
            return self._pyproject_has_table("tool", "codespell")
        return False

    def _pyproject_has_table(self, *keys: str) -> bool:
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists():
            return False
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return False
        node = data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return True
