"""Pydantic models for tools, checks, suites, and failure reports."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"


class InstallMethod(str, Enum):
    PIP = "pip"
    NPM = "npm"
    SYSTEM = "system"
    SKIP = "skip"


class EnvMode(str, Enum):
    MANAGED = "managed"
    PROJECT = "project"
    AUTO = "auto"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class InstallSpec(BaseModel):
    method: InstallMethod
    package: str | None = None
    version: str | None = None


class ToolConfigSpec(BaseModel):
    """Declarative config discovery for a tool (repo-native vs bundled)."""

    flag: str | None = None
    pass_flag: bool | None = None
    bundled: str | None = None
    bundled_path: str | None = None
    repo_files: list[str] = Field(default_factory=list)
    repo_dirs: list[str] = Field(default_factory=list)
    pyproject: list[str] = Field(default_factory=list)
    use_pyproject_as_path: bool = False

    def should_pass_flag(self) -> bool:
        if self.pass_flag is not None:
            return self.pass_flag
        return bool(self.flag)


class IgnoreKind(str, Enum):
    FLAG_PAIRS = "flag_pairs"
    PREFIX = "prefix"
    SKIP_FILE = "skip_file"
    CONFIG_OVERLAY = "config_overlay"


class ExtendFrom(str, Enum):
    NONE = "none"
    BASE_CONFIG = "base_config"
    BASE_OR_PYPROJECT = "base_or_pyproject"
    PYPROJECT = "pyproject"


class ToolIgnoreSpec(BaseModel):
    """How this tool consumes unified ignore patterns."""

    kind: IgnoreKind
    flag: str | None = None
    prefix: str | None = None
    post_subcommand: bool = False
    format: str | None = None
    file: str | None = None
    key: str | None = None
    key_style: str = "list"
    extend_from: ExtendFrom = ExtendFrom.NONE
    extend_key: str | None = None
    toml_table: str | None = None


class ToolDef(BaseModel):
    id: str
    name: str
    description: str
    install: InstallSpec
    binary: str
    documentation_url: str | None = None
    config: ToolConfigSpec | None = None
    ignore: ToolIgnoreSpec | None = None


class SuccessCriteria(BaseModel):
    exit_codes: list[int] = Field(default_factory=lambda: [0])


class CheckPolicy(BaseModel):
    max_complexity_rank: str | None = None
    max_duplication_percent: float | None = None
    min_coverage_percent: float | None = None
    coverage_source: str | None = None
    min_confidence: int | None = None


class ConfigMode(str, Enum):
    AUTO = "auto"
    BUNDLED = "bundled"
    PATHS = "paths"


class ConfigSpec(BaseModel):
    mode: ConfigMode = ConfigMode.AUTO
    paths: dict[str, str] = Field(default_factory=dict)


class IgnoreSpec(BaseModel):
    """Repo-wide ignore rules merged across suite, project, and per-check layers."""

    model_config = ConfigDict(populate_by_name=True)

    ignore_profile: list[str] = Field(default_factory=list, alias="ignore-profile")
    ignore_paths: list[str] = Field(default_factory=list, alias="ignore-paths")


class GateConfigSpec(BaseModel):
    """Declarative policy-config discovery for script gates."""

    bundled: str | None = None
    project_file: str | None = None
    allowlist_bundled: str | None = None


class CheckDef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tool: str
    name: str
    description: str
    argv: list[str] = Field(default_factory=list)
    parser: str
    script: str | None = None
    include: list[str] = Field(default_factory=list)
    config: GateConfigSpec | None = None
    success: SuccessCriteria = Field(default_factory=SuccessCriteria)
    policy: CheckPolicy | None = None
    remediation: dict[str, Any] = Field(default_factory=dict)
    output_file: str | None = None
    ignore_profile: list[str] = Field(default_factory=list, alias="ignore-profile")
    ignore_paths: list[str] = Field(default_factory=list, alias="ignore-paths")

    @model_validator(mode="after")
    def validate_script_gate(self) -> CheckDef:
        if self.tool == "script" and not self.script:
            raise ValueError(f"Check '{self.id}' uses tool 'script' but has no script path")
        return self


class SuiteCheckRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    target: str | None = None
    ignore_profile: list[str] = Field(default_factory=list, alias="ignore-profile")
    ignore_paths: list[str] = Field(default_factory=list, alias="ignore-paths")


class SuiteDef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    env: EnvMode = EnvMode.AUTO
    checks: list[SuiteCheckRef]
    target: str = "."
    ignore_profile: list[str] = Field(default_factory=list, alias="ignore-profile")
    ignore_paths: list[str] = Field(default_factory=list, alias="ignore-paths")


class ProjectConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    suite: str
    env: EnvMode = EnvMode.AUTO
    target: str = "."
    checks: list[SuiteCheckRef] = Field(default_factory=list)
    configs: ConfigSpec = Field(default_factory=ConfigSpec)
    ignore_profile: list[str] = Field(default_factory=list, alias="ignore-profile")
    ignore_paths: list[str] = Field(default_factory=list, alias="ignore-paths")


class Location(BaseModel):
    file: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None


class FixHint(BaseModel):
    description: str | None = None
    command: str | None = None


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    location: Location | None = None
    snippet: str | None = None
    fix: FixHint | None = None


class FailureSummary(BaseModel):
    finding_count: int
    by_severity: dict[str, int] = Field(default_factory=dict)


class Remediation(BaseModel):
    docs_url: str | None = None
    suggested_commands: list[str] = Field(default_factory=list)


class FailureArtifacts(BaseModel):
    raw_stdout: str | None = None
    raw_stderr: str | None = None


class FailureReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    check_id: str
    tool_id: str
    status: str = "failed"
    suite_id: str | None = None
    target: str
    started_at: datetime
    duration_ms: int
    summary: FailureSummary
    findings: list[Finding]
    remediation: Remediation = Field(default_factory=Remediation)
    artifacts: FailureArtifacts = Field(default_factory=FailureArtifacts)


class CheckResult(BaseModel):
    check_id: str
    passed: bool
    report_path: str | None = None
    error: str | None = None


class SuiteResult(BaseModel):
    suite_id: str
    passed: bool
    results: list[CheckResult] = Field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def summarize_findings(findings: list[Finding]) -> FailureSummary:
    by_severity: dict[str, int] = {}
    for finding in findings:
        key = finding.severity.value
        by_severity[key] = by_severity.get(key, 0) + 1
    return FailureSummary(finding_count=len(findings), by_severity=by_severity)
