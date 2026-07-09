"""Load and validate catalog definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

from pyaitools.models import CheckDef, ProjectConfig, SuiteDef, ToolDef

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = PACKAGE_ROOT / "catalog"
SUITES_ROOT = PACKAGE_ROOT / "suites"
PROJECT_CATALOG = ".pyaitools/catalog"
PROJECT_SUITES = ".pyaitools/suites"


class Registry:
    def __init__(self, root: Path | None = None, project_root: Path | None = None) -> None:
        self.root = root or PACKAGE_ROOT
        self.project_root = (project_root or Path.cwd()).resolve()
        self.catalog_root = self.root / "catalog"
        self.suites_root = self.root / "suites"
        self.tools: dict[str, ToolDef] = {}
        self.checks: dict[str, CheckDef] = {}
        self.suites: dict[str, SuiteDef] = {}
        self._load()

    def _load_yaml_dir(self, directory: Path) -> dict[str, dict]:
        items: dict[str, dict] = {}
        if not directory.exists():
            return items
        for path in sorted(directory.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            items[data["id"]] = data
        return items

    def _load(self) -> None:
        for tool_id, data in self._load_yaml_dir(self.catalog_root / "tools").items():
            self.tools[tool_id] = ToolDef.model_validate(data)
        for check_id, data in self._load_yaml_dir(self.catalog_root / "checks").items():
            self.checks[check_id] = CheckDef.model_validate(data)
        for suite_id, data in self._load_yaml_dir(self.suites_root).items():
            self.suites[suite_id] = SuiteDef.model_validate(data)

        project_catalog = self.project_root / PROJECT_CATALOG
        for tool_id, data in self._load_yaml_dir(project_catalog / "tools").items():
            self.tools[tool_id] = ToolDef.model_validate(data)
        for check_id, data in self._load_yaml_dir(project_catalog / "checks").items():
            self.checks[check_id] = CheckDef.model_validate(data)

        project_suites = self.project_root / PROJECT_SUITES
        for suite_id, data in self._load_yaml_dir(project_suites).items():
            self.suites[suite_id] = SuiteDef.model_validate(data)

    def get_tool(self, tool_id: str) -> ToolDef:
        if tool_id not in self.tools:
            raise KeyError(f"Unknown tool: {tool_id}")
        return self.tools[tool_id]

    def get_check(self, check_id: str) -> CheckDef:
        if check_id not in self.checks:
            raise KeyError(f"Unknown check: {check_id}")
        return self.checks[check_id]

    def get_suite(self, suite_id: str) -> SuiteDef:
        if suite_id not in self.suites:
            raise KeyError(f"Unknown suite: {suite_id}")
        return self.suites[suite_id]

    def load_project_config(self, project_root: Path | None = None) -> ProjectConfig | None:
        root = project_root or self.project_root
        config_path = root / "pyaitools.yaml"
        if not config_path.exists():
            return None
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return ProjectConfig.model_validate(data)

    def project_gate_checks(self) -> list[CheckDef]:
        return [check for check in self.checks.values() if check.tool == "script"]
