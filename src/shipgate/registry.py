"""Load and validate catalog definitions."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from shipgate.constants import (
    CONFIG_FILENAME,
    LEGACY_CONFIG_FILENAME,
    LEGACY_RUNTIME_DIR,
    PROJECT_CATALOG,
    PROJECT_SUITES,
    RUNTIME_DIR,
)
from shipgate.models import CheckDef, ProjectConfig, SuiteDef, ToolDef

BUNDLE_ROOT = Path(__file__).resolve().parent / "bundle"

_LEGACY_CONFIG_WARNED = False


def project_runtime_dir(project_root: Path) -> Path:
    """Return active runtime dir, preferring ``.shipgate`` over legacy ``.pyossmtool``."""
    primary = project_root / RUNTIME_DIR
    if primary.exists():
        return primary
    legacy = project_root / LEGACY_RUNTIME_DIR
    if legacy.exists():
        return legacy
    return primary


class Registry:
    def __init__(self, root: Path | None = None, project_root: Path | None = None) -> None:
        self.root = root or BUNDLE_ROOT
        self.project_root = (project_root or Path.cwd()).resolve()
        self.catalog_root = self.root / "catalog"
        self.suites_root = self.root / "suites"
        self.tools: dict[str, ToolDef] = {}
        self.checks: dict[str, CheckDef] = {}
        self.suites: dict[str, SuiteDef] = {}
        self._check_aliases: dict[str, str] = {}
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
        self._load_catalog_tree(self.catalog_root, self.suites_root)
        runtime = project_runtime_dir(self.project_root)
        project_catalog = runtime / PROJECT_CATALOG.split("/", 1)[1]
        project_suites = runtime / PROJECT_SUITES.split("/", 1)[1]
        self._load_catalog_tree(project_catalog, project_suites)
        self._build_check_aliases()

    def _build_check_aliases(self) -> None:
        self._check_aliases.clear()
        for check_id, check in self.checks.items():
            for alias in check.aliases:
                self._check_aliases[alias] = check_id

    def _load_catalog_tree(self, catalog_root: Path, suites_root: Path) -> None:
        for tool_id, data in self._load_yaml_dir(catalog_root / "tools").items():
            self.tools[tool_id] = ToolDef.model_validate(data)
        for check_id, data in self._load_yaml_dir(catalog_root / "checks").items():
            self.checks[check_id] = CheckDef.model_validate(data)
        for suite_id, data in self._load_yaml_dir(suites_root).items():
            self.suites[suite_id] = SuiteDef.model_validate(data)

    def get_tool(self, tool_id: str) -> ToolDef:
        if tool_id not in self.tools:
            raise KeyError(f"Unknown tool: {tool_id}")
        return self.tools[tool_id]

    def resolve_check_id(self, check_id: str) -> str:
        return self._check_aliases.get(check_id, check_id)

    def get_check(self, check_id: str) -> CheckDef:
        resolved = self.resolve_check_id(check_id)
        if resolved not in self.checks:
            raise KeyError(f"Unknown check: {check_id}")
        return self.checks[resolved]

    def get_suite(self, suite_id: str) -> SuiteDef:
        if suite_id not in self.suites:
            raise KeyError(f"Unknown suite: {suite_id}")
        return self.suites[suite_id]

    def load_project_config(self, project_root: Path | None = None) -> ProjectConfig | None:
        global _LEGACY_CONFIG_WARNED
        root = project_root or self.project_root
        config_path = root / CONFIG_FILENAME
        if not config_path.exists():
            legacy_path = root / LEGACY_CONFIG_FILENAME
            if legacy_path.exists():
                if not _LEGACY_CONFIG_WARNED:
                    print(
                        f"WARN: {LEGACY_CONFIG_FILENAME} is deprecated; rename to {CONFIG_FILENAME}",
                        file=sys.stderr,
                    )
                    _LEGACY_CONFIG_WARNED = True
                config_path = legacy_path
            else:
                return None
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return ProjectConfig.model_validate(data)
