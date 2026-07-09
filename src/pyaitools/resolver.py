"""Hybrid binary resolution for quality tools."""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from pyaitools.models import EnvMode, ToolDef


class BinaryResolver:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.cache_root = Path.home() / ".cache" / "pyaitools" / "tools"
        self.local_tools_root = self.project_root / ".pyaitools" / "tools"

    def resolve_env_mode(self, mode: EnvMode) -> EnvMode:
        if mode != EnvMode.AUTO:
            return mode
        if self._project_venv_exists():
            return EnvMode.PROJECT
        return EnvMode.MANAGED

    def _project_venv_exists(self) -> bool:
        return (self.project_root / "pyproject.toml").exists() and (
            (self.project_root / ".venv").exists() or (self.project_root / "venv").exists()
        )

    def _venv_bin_dirs(self) -> list[Path]:
        candidates = [
            self.project_root / ".pyaitools" / "tools" / "venv" / "bin",
            self.project_root / ".venv" / "bin",
            self.project_root / "venv" / "bin",
            self.local_tools_root / "bin",
            self.cache_root / "bin",
        ]
        return [path for path in candidates if path.is_dir()]

    def _tool_in_project_deps(self, tool: ToolDef) -> bool:
        pyproject = self.project_root / "pyproject.toml"
        if not pyproject.exists() or tool.install.package is None:
            return False
        package_name = tool.install.package.split(">=")[0].split("==")[0].strip()
        text = pyproject.read_text(encoding="utf-8")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return package_name in text
        dep_groups = data.get("dependency-groups", {})
        project_deps = data.get("project", {}).get("dependencies", [])
        all_deps = list(project_deps)
        for group in dep_groups.values():
            if isinstance(group, list):
                all_deps.extend(group)
        return any(package_name in dep for dep in all_deps)

    def resolve(self, tool: ToolDef, mode: EnvMode) -> Path:
        resolved_mode = self.resolve_env_mode(mode)
        if resolved_mode == EnvMode.PROJECT:
            binary = self._resolve_from_path(tool.binary)
            if binary is not None:
                return binary
            if tool.install.method.value == "npm":
                binary = self._resolve_npm(tool.binary)
                if binary is not None:
                    return binary
        if resolved_mode == EnvMode.AUTO and self._tool_in_project_deps(tool):
            binary = self._resolve_from_path(tool.binary)
            if binary is not None:
                return binary

        binary = self._resolve_managed(tool)
        if binary is not None:
            return binary

        found = shutil.which(tool.binary)
        if found:
            return Path(found)

        if tool.install.method.value == "system":
            binary = self._resolve_system(tool.binary)
            if binary is not None:
                return binary

        raise FileNotFoundError(
            f"Could not resolve binary '{tool.binary}' for tool '{tool.id}' (mode={resolved_mode.value})"
        )

    def _resolve_from_path(self, binary_name: str) -> Path | None:
        for bin_dir in self._venv_bin_dirs():
            candidate = bin_dir / binary_name
            if candidate.exists():
                return candidate
        found = shutil.which(binary_name)
        if found:
            return Path(found)
        return None

    def _resolve_npm(self, binary_name: str) -> Path | None:
        local = self.project_root / "node_modules" / ".bin" / binary_name
        if local.exists():
            return local
        return self._resolve_from_path(binary_name)

    def _resolve_managed(self, tool: ToolDef) -> Path | None:
        managed_venv_bin = self.project_root / ".pyaitools" / "tools" / "venv" / "bin"
        if managed_venv_bin.is_dir():
            candidate = managed_venv_bin / tool.binary
            if candidate.exists():
                return candidate
        for bin_dir in [self.local_tools_root / "bin", self.cache_root / "bin"]:
            candidate = bin_dir / tool.binary
            if candidate.exists():
                return candidate
        return None

    def _resolve_system(self, binary_name: str) -> Path | None:
        found = shutil.which(binary_name)
        if found:
            return Path(found)
        trunk_glob = Path.home() / ".cache" / "trunk" / "repos"
        if trunk_glob.exists():
            matches = sorted(trunk_glob.glob(f"*/tools/{binary_name}"))
            if matches:
                return matches[-1]
        return None

    def prepend_managed_path(self, env: dict[str, str] | None = None) -> dict[str, str]:
        merged = dict(env or os.environ)
        paths = [str(path) for path in self._venv_bin_dirs()]
        merged["PATH"] = os.pathsep.join(paths + [merged.get("PATH", "")])
        return merged
