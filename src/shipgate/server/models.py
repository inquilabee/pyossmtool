"""Pydantic models for report-server runs and findings."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FindingCategory(StrEnum):
    CODE = "code"
    TOOL = "tool"


class RunSummaryRecord(BaseModel):
    finding_count: int
    tool_failure_count: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_check_id: dict[str, int] = Field(default_factory=dict)


class FindingRecord(BaseModel):
    id: str
    run_id: str
    check_id: str
    tool_id: str
    rule_id: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    docs_url: str | None = None
    suggested_commands: list[str] = Field(default_factory=list)
    category: FindingCategory = FindingCategory.CODE


class RunRecord(BaseModel):
    id: str
    branch: str
    suite_id: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    worktree_path: str | None = None
    error_message: str | None = None
    current_check_id: str | None = None
    checks_completed: int = 0
    checks_total: int = 0
    summary: RunSummaryRecord | None = None
