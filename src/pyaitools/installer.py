"""Install quality tool dependencies into managed environments."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from pyaitools.models import EnvMode, InstallMethod, SuiteDef, ToolDef
from pyaitools.registry import Registry
from pyaitools.resolver import BinaryResolver


class Installer:
    def __init__(self, registry: Registry, project_root: Path | None = None) -> None:
        self.registry = registry
        self.project_root = (project_root or Path.cwd()).resolve()
        self.resolver = BinaryResolver(self.project_root)
        self.managed_venv = self.project_root / ".pyaitools" / "tools" / "venv"

    def tools_for_suite(self, suite: SuiteDef) -> list[ToolDef]:
        tool_ids: set[str] = set()
        for check_ref in suite.checks:
            check = self.registry.get_check(check_ref.id)
            tool_ids.add(check.tool)
        return [self.registry.get_tool(tool_id) for tool_id in sorted(tool_ids)]

    def install_suite(self, suite_id: str) -> None:
        suite = self.registry.get_suite(suite_id)
        for tool in self.tools_for_suite(suite):
            self.install_tool(tool)

    def install_tool(self, tool: ToolDef) -> None:
        method = tool.install.method
        handlers = {
            InstallMethod.SKIP: lambda _tool: None,
            InstallMethod.SYSTEM: self._warn_missing_system_tool,
            InstallMethod.PIP: self._install_pip_tool,
            InstallMethod.NPM: self._install_npm_tool,
        }
        handler = handlers.get(method)
        if handler is None:
            raise RuntimeError(f"Unsupported install method: {method}")
        handler(tool)

    def _install_npm_tool(self, tool: ToolDef) -> None:
        if self._binary_available(tool):
            return
        self._install_npm(tool)
        self._require_binary(tool)

    def _warn_missing_system_tool(self, tool: ToolDef) -> None:
        if self.resolver._resolve_system(tool.binary) is not None:
            return
        print(
            f"WARN: system tool '{tool.binary}' not found; install manually to enable related checks",
            file=sys.stderr,
        )

    def _install_pip_tool(self, tool: ToolDef) -> None:
        self._ensure_managed_venv()
        self._install_pip(tool)
        self._require_binary(tool)

    def _require_binary(self, tool: ToolDef) -> None:
        if self._binary_available(tool):
            return
        raise RuntimeError(f"Failed to install tool '{tool.id}' ({tool.binary})")

    def _binary_available(self, tool: ToolDef) -> bool:
        try:
            self.resolver.resolve(tool, mode=EnvMode.MANAGED)
            return True
        except FileNotFoundError:
            return False

    def _managed_python(self) -> str:
        if sys.version_info < (3, 14):
            return sys.executable
        for candidate in ("python3.13", "python3.12", "python3.11"):
            found = shutil.which(candidate)
            if found:
                return found
        return sys.executable

    def _ensure_managed_venv(self) -> None:
        python_bin = self.managed_venv / "bin" / "python"
        if python_bin.exists():
            version = subprocess.run(
                [str(python_bin), "--version"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            if "3.14" in version:
                shutil.rmtree(self.managed_venv)
        if (self.managed_venv / "bin" / "python").exists():
            return
        self.managed_venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([self._managed_python(), "-m", "venv", str(self.managed_venv)], check=True)

    def _install_pip(self, tool: ToolDef) -> None:
        pip = self.managed_venv / "bin" / "pip"
        packages = (tool.install.package or tool.id).split()
        subprocess.run([str(pip), "install", "--upgrade", *packages], check=True)

    def _install_npm(self, tool: ToolDef) -> None:
        package = tool.install.package or tool.id
        subprocess.run(["npm", "install", "-g", package], check=True)
