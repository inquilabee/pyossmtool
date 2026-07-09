"""Install quality tool dependencies into managed environments."""

from __future__ import annotations

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
        if tool.install.method == InstallMethod.SKIP:
            return

        if tool.install.method == InstallMethod.SYSTEM:
            if self.resolver._resolve_system(tool.binary) is None:
                import sys
                print(
                    f"WARN: system tool '{tool.binary}' not found; install manually to enable related checks",
                    file=sys.stderr,
                )
            return

        if self._binary_available(tool):
            return

        if tool.install.method == InstallMethod.PIP:
            self._ensure_managed_venv()
            self._install_pip(tool)
        elif tool.install.method == InstallMethod.NPM:
            self._install_npm(tool)
        else:
            raise RuntimeError(f"Unsupported install method: {tool.install.method}")

        if not self._binary_available(tool):
            raise RuntimeError(f"Failed to install tool '{tool.id}' ({tool.binary})")

    def _binary_available(self, tool: ToolDef) -> bool:
        try:
            self.resolver.resolve(tool, mode=EnvMode.MANAGED)
            return True
        except FileNotFoundError:
            return False

    def _ensure_managed_venv(self) -> None:
        if (self.managed_venv / "bin" / "python").exists():
            return
        self.managed_venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(self.managed_venv)], check=True)

    def _install_pip(self, tool: ToolDef) -> None:
        pip = self.managed_venv / "bin" / "pip"
        packages = (tool.install.package or tool.id).split()
        subprocess.run([str(pip), "install", "--upgrade", *packages], check=True)

    def _install_npm(self, tool: ToolDef) -> None:
        package = tool.install.package or tool.id
        subprocess.run(["npm", "install", "-g", package], check=True)
