"""Pydantic models for tools, checks, suites, and failure reports."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class ToolDef(BaseModel):
    id: str
    name: str
    description: str
    install: InstallSpec
    binary: str
    documentation_url: str | None = None


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


class CheckDef(BaseModel):
    id: str
    tool: str
    name: str
    description: str
    argv: list[str] = Field(default_factory=list)
    parser: str
    script: str | None = None
    target_key: str = "python"
    success: SuccessCriteria = Field(default_factory=SuccessCriteria)
    policy: CheckPolicy | None = None
    remediation: dict[str, Any] = Field(default_factory=dict)
    output_file: str | None = None

    @model_validator(mode="after")
    def validate_script_gate(self) -> CheckDef:
        if self.tool == "script" and not self.script:
            raise ValueError(f"Check '{self.id}' uses tool 'script' but has no script path")
        return self


class SuiteCheckRef(BaseModel):
    id: str
    target: str | None = None


class SuiteDef(BaseModel):
    id: str
    name: str
    description: str
    env: EnvMode = EnvMode.AUTO
    checks: list[SuiteCheckRef]
    targets: dict[str, str] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    suite: str
    env: EnvMode = EnvMode.AUTO
    targets: dict[str, str] = Field(default_factory=dict)
    checks: list[SuiteCheckRef] = Field(default_factory=list)
    configs: ConfigSpec = Field(default_factory=ConfigSpec)


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
