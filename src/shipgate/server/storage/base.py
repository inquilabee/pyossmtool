"""Storage protocol for report-server runs and findings."""

from __future__ import annotations

from typing import Protocol

from shipgate.server.models import FindingCategory, FindingRecord, RunRecord, RunStatus, RunSummaryRecord

MAX_RUNS = 50


class Storage(Protocol):
    def create_run(self, *, branch: str, suite_id: str, worktree_path: str | None = None) -> RunRecord: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def list_runs(self, *, limit: int = 50, branch: str | None = None) -> list[RunRecord]: ...

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        worktree_path: str | None = None,
        error_message: str | None = None,
        current_check_id: str | None = None,
        checks_completed: int | None = None,
        checks_total: int | None = None,
        finished: bool = False,
        summary: RunSummaryRecord | None = None,
    ) -> RunRecord: ...

    def replace_findings(self, run_id: str, findings: list[FindingRecord]) -> None: ...

    def list_findings(
        self,
        run_id: str,
        *,
        severity: str | None = None,
        check_id: str | None = None,
        file: str | None = None,
        category: FindingCategory | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[FindingRecord]: ...

    def count_findings(
        self,
        run_id: str,
        *,
        severity: str | None = None,
        check_id: str | None = None,
        file: str | None = None,
        category: FindingCategory | None = None,
    ) -> int: ...

    def previous_completed_run(self, *, branch: str, before_run_id: str) -> RunRecord | None: ...

    def prune_old_runs(self, keep: int = 50) -> int: ...
