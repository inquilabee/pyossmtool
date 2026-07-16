"""Hybrid binary resolution for quality tools."""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from pyossmtool.models import EnvMode, ToolDef


class BinaryResolver:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.cache_root = Path.home() / ".cache" / "pyossmtool" / "tools"
        self.local_tools_root = self.project_root / ".pyossmtool" / "tools"

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
            self.project_root / ".pyossmtool" / "tools" / "venv" / "bin",
            self.project_root / ".pyossmtool" / "tools" / "npm" / "node_modules" / ".bin",
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
        return package_name in self._project_dependency_text(pyproject)

    def _project_dependency_text(self, pyproject: Path) -> str:
        text = pyproject.read_text(encoding="utf-8")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return text
        deps = list(data.get("project", {}).get("dependencies", []))
        for group in data.get("dependency-groups", {}).values():
            if isinstance(group, list):
                deps.extend(group)
        return " ".join(deps)

    def resolve(self, tool: ToolDef, mode: EnvMode) -> Path:
        resolved_mode = self.resolve_env_mode(mode)
        for candidate in self._resolution_candidates(tool, resolved_mode):
            if candidate is not None:
                return candidate
        raise FileNotFoundError(
            f"Could not resolve binary '{tool.binary}' for tool '{tool.id}' (mode={resolved_mode.value})"
        )

    def _resolution_candidates(self, tool: ToolDef, mode: EnvMode):
        yield self._resolve_for_mode(tool, mode)
        yield self._resolve_managed(tool)
        yield self._resolve_which(tool.binary)
        if tool.install.method.value == "system":
            yield self._resolve_system(tool.binary)

    def _resolve_for_mode(self, tool: ToolDef, mode: EnvMode) -> Path | None:
        if mode == EnvMode.PROJECT:
            return self._resolve_project_paths(tool)
        if mode == EnvMode.AUTO and self._tool_in_project_deps(tool):
            return self._resolve_from_path(tool.binary)
        return None

    def _resolve_project_paths(self, tool: ToolDef) -> Path | None:
        binary = self._resolve_from_path(tool.binary)
        if binary is not None:
            return binary
        if tool.install.method.value == "npm":
            return self._resolve_npm(tool.binary)
        return None

    def _resolve_which(self, binary_name: str) -> Path | None:
        found = shutil.which(binary_name)
        return Path(found) if found else None

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
        managed = self.project_root / ".pyossmtool" / "tools" / "npm" / "node_modules" / ".bin" / binary_name
        if managed.exists():
            return managed
        local = self.project_root / "node_modules" / ".bin" / binary_name
        if local.exists():
            return local
        return self._resolve_from_path(binary_name)

    def _resolve_managed(self, tool: ToolDef) -> Path | None:
        managed_venv_bin = self.project_root / ".pyossmtool" / "tools" / "venv" / "bin"
        if managed_venv_bin.is_dir():
            candidate = managed_venv_bin / tool.binary
            if candidate.exists():
                return candidate
        if tool.install.method.value == "npm":
            npm_bin = self._resolve_npm(tool.binary)
            if npm_bin is not None:
                return npm_bin
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
