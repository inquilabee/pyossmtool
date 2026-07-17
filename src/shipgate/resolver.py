"""Hybrid binary resolution for quality tools."""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path

from shipgate.constants import PROJECT_TOOLS_DIR, RUNTIME_DIR
from shipgate.models import EnvMode, ToolDef


def _dedup_existing_dirs(candidates: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if not path.is_dir() or resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(path)
    return ordered


class BinaryResolver:
    def __init__(self, project_root: Path | None = None, tools_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.tools_root = (tools_root or self.project_root).resolve()
        self.cache_root = Path.home() / ".cache" / "shipgate" / "tools"
        self.local_tools_root = self.tools_root / PROJECT_TOOLS_DIR

    def resolve_env_mode(self, mode: EnvMode) -> EnvMode:
        if mode != EnvMode.AUTO:
            return mode
        if self._project_env_available():
            return EnvMode.PROJECT
        return EnvMode.MANAGED

    def _project_env_available(self) -> bool:
        return bool(self._project_venv_bin_dirs())

    def _venv_bin_dirs(self) -> list[Path]:
        candidates = [
            self.tools_root / RUNTIME_DIR / "tools" / "venv" / "bin",
            self.tools_root / RUNTIME_DIR / "tools" / "npm" / "node_modules" / ".bin",
            *self._project_venv_bin_dirs(),
            self.local_tools_root / "bin",
            self.cache_root / "bin",
        ]
        return [path for path in candidates if path.is_dir()]

    def _project_venv_bin_dirs(self) -> list[Path]:
        """Bin dirs for the user's project environment (any name).

        Order:
        1. ``VIRTUAL_ENV`` when set (active activated env)
        2. Directory of the running interpreter (``sys.executable``)
        3. Conventional ``.venv`` / ``venv`` under tools_root then project_root
        """
        candidates: list[Path] = []
        virtual_env = os.environ.get("VIRTUAL_ENV")
        if virtual_env:
            root = Path(virtual_env)
            candidates.extend([root / "bin", root / "Scripts"])
        exe_bin = Path(sys.executable).resolve().parent
        if exe_bin.name in {"bin", "Scripts"}:
            candidates.append(exe_bin)
        for root in (self.tools_root, self.project_root):
            candidates.extend(
                [
                    root / ".venv" / "bin",
                    root / ".venv" / "Scripts",
                    root / "venv" / "bin",
                    root / "venv" / "Scripts",
                ]
            )
        return _dedup_existing_dirs(candidates)

    def project_env_bin_dirs(self) -> list[Path]:
        """Public accessor for project-environment bin directories."""
        return self._project_venv_bin_dirs()

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
        for bin_dir in self._project_venv_bin_dirs():
            candidate = bin_dir / tool.binary
            if candidate.exists():
                return candidate
        if tool.install.method.value == "npm":
            return self._resolve_npm(tool.binary)
        found = shutil.which(tool.binary)
        return Path(found) if found else None

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
        managed = self.tools_root / RUNTIME_DIR / "tools" / "npm" / "node_modules" / ".bin" / binary_name
        if managed.exists():
            return managed
        local = self.project_root / "node_modules" / ".bin" / binary_name
        if local.exists():
            return local
        return self._resolve_from_path(binary_name)

    def _resolve_managed(self, tool: ToolDef) -> Path | None:
        managed = self._resolve_managed_venv(tool)
        if managed is not None:
            return managed
        if tool.install.method.value == "npm":
            npm_bin = self._resolve_npm(tool.binary)
            if npm_bin is not None:
                return npm_bin
        return self._resolve_fallback_bin(tool)

    def _resolve_managed_venv(self, tool: ToolDef) -> Path | None:
        managed_venv_bin = self.tools_root / RUNTIME_DIR / "tools" / "venv" / "bin"
        if not managed_venv_bin.is_dir():
            return None
        candidate = managed_venv_bin / tool.binary
        return candidate if candidate.exists() else None

    def _resolve_fallback_bin(self, tool: ToolDef) -> Path | None:
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
