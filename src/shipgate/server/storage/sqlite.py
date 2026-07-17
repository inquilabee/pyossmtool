"""SQLite implementation of the report-server Storage protocol."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from shipgate.models import utc_now
from shipgate.paths import normalize_finding_path
from shipgate.server.models import FindingCategory, FindingRecord, RunRecord, RunStatus, RunSummaryRecord
from shipgate.server.storage.base import MAX_RUNS

_COMPLETED_STATUSES = (
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
)


class SqliteStorage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    branch TEXT NOT NULL,
                    suite_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    worktree_path TEXT,
                    error_message TEXT,
                    current_check_id TEXT,
                    checks_completed INTEGER NOT NULL DEFAULT 0,
                    checks_total INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    check_id TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    file TEXT,
                    line INTEGER,
                    column_num INTEGER,
                    docs_url TEXT,
                    suggested_commands_json TEXT NOT NULL DEFAULT '[]',
                    category TEXT NOT NULL DEFAULT 'code',
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
                CREATE INDEX IF NOT EXISTS idx_runs_branch ON runs(branch);
                CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(findings)").fetchall()}
            if "category" not in columns:
                conn.execute("ALTER TABLE findings ADD COLUMN category TEXT NOT NULL DEFAULT 'code'")

    def create_run(
        self,
        *,
        branch: str,
        suite_id: str,
        worktree_path: str | None = None,
    ) -> RunRecord:
        run = RunRecord(
            id=uuid.uuid4().hex,
            branch=branch,
            suite_id=suite_id,
            status=RunStatus.QUEUED,
            started_at=utc_now(),
            worktree_path=worktree_path,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, branch, suite_id, status, started_at, finished_at, duration_ms,
                    worktree_path, error_message, current_check_id,
                    checks_completed, checks_total, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.branch,
                    run.suite_id,
                    run.status.value,
                    _dt_to_iso(run.started_at),
                    None,
                    None,
                    run.worktree_path,
                    None,
                    None,
                    run.checks_completed,
                    run.checks_total,
                    None,
                ),
            )
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def list_runs(self, *, limit: int = 50, branch: str | None = None) -> list[RunRecord]:
        query = "SELECT * FROM runs"
        params: list[object] = []
        if branch is not None:
            query += " WHERE branch = ?"
            params.append(branch)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_run(row) for row in rows]

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
    ) -> RunRecord:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        _apply_run_fields(
            run,
            {
                "status": status,
                "worktree_path": worktree_path,
                "error_message": error_message,
                "current_check_id": current_check_id,
                "checks_completed": checks_completed,
                "checks_total": checks_total,
                "summary": summary,
            },
        )
        if finished:
            _mark_run_finished(run)
        self._persist_run(run, run_id)
        return run

    def _persist_run(self, run: RunRecord, run_id: str) -> None:
        summary_json = None if run.summary is None else run.summary.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    finished_at = ?,
                    duration_ms = ?,
                    worktree_path = ?,
                    error_message = ?,
                    current_check_id = ?,
                    checks_completed = ?,
                    checks_total = ?,
                    summary_json = ?
                WHERE id = ?
                """,
                (
                    run.status.value,
                    _dt_to_iso(run.finished_at) if run.finished_at else None,
                    run.duration_ms,
                    run.worktree_path,
                    run.error_message,
                    run.current_check_id,
                    run.checks_completed,
                    run.checks_total,
                    summary_json,
                    run_id,
                ),
            )

    def replace_findings(self, run_id: str, findings: list[FindingRecord]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM findings WHERE run_id = ?", (run_id,))
            conn.executemany(
                """
                INSERT INTO findings (
                    id, run_id, check_id, tool_id, rule_id, severity, message,
                    file, line, column_num, docs_url, suggested_commands_json, category
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f.id,
                        f.run_id,
                        f.check_id,
                        f.tool_id,
                        f.rule_id,
                        f.severity,
                        f.message,
                        f.file,
                        f.line,
                        f.column,
                        f.docs_url,
                        json.dumps(f.suggested_commands),
                        f.category.value,
                    )
                    for f in findings
                ],
            )

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
    ) -> list[FindingRecord]:
        query, params = _findings_filter_query(
            run_id,
            severity=severity,
            check_id=check_id,
            file=file,
            category=category,
        )
        query += " ORDER BY file, line, id"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_finding(row) for row in rows]

    def count_findings(
        self,
        run_id: str,
        *,
        severity: str | None = None,
        check_id: str | None = None,
        file: str | None = None,
        category: FindingCategory | None = None,
    ) -> int:
        where, params = _findings_filter_clause(
            run_id,
            severity=severity,
            check_id=check_id,
            file=file,
            category=category,
        )
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM findings WHERE {where}", params).fetchone()  # nosec B608
        return int(row[0])

    def previous_completed_run(self, *, branch: str, before_run_id: str) -> RunRecord | None:
        before = self.get_run(before_run_id)
        if before is None:
            return None
        placeholders = ", ".join("?" for _ in _COMPLETED_STATUSES)
        query = (
            "SELECT * FROM runs WHERE branch = ? "
            f"AND status IN ({placeholders}) "  # nosec B608
            "AND started_at < ? ORDER BY started_at DESC LIMIT 1"
        )
        with self._connect() as conn:
            row = conn.execute(
                query,
                (branch, *_COMPLETED_STATUSES, _dt_to_iso(before.started_at)),
            ).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def prune_old_runs(self, keep: int = MAX_RUNS) -> int:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            if total <= keep:
                return 0
            to_delete = total - keep
            rows = conn.execute(
                """
                SELECT id FROM runs
                ORDER BY started_at ASC
                LIMIT ?
                """,
                (to_delete,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return 0
            placeholders = ", ".join("?" for _ in ids)
            conn.execute(f"DELETE FROM findings WHERE run_id IN ({placeholders})", ids)  # nosec B608
            conn.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", ids)  # nosec B608
            return len(ids)


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _findings_filter_clause(
    run_id: str,
    *,
    severity: str | None,
    check_id: str | None,
    file: str | None,
    category: FindingCategory | None,
) -> tuple[str, list[object]]:
    clauses = ["run_id = ?"]
    params: list[object] = [run_id]
    _append_clause(clauses, params, "severity = ?", severity)
    _append_clause(clauses, params, "check_id = ?", check_id)
    if file is not None:
        normalized = normalize_finding_path(file) or file
        clauses.append("file LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(normalized)}%")
    _append_clause(clauses, params, "category = ?", category.value if category else None)
    return " AND ".join(clauses), params


def _append_clause(clauses: list[str], params: list[object], clause: str, value: object | None) -> None:
    if value is None:
        return
    clauses.append(clause)
    params.append(value)


def _findings_filter_query(
    run_id: str,
    *,
    severity: str | None,
    check_id: str | None,
    file: str | None,
    category: FindingCategory | None,
) -> tuple[str, list[object]]:
    where, params = _findings_filter_clause(
        run_id,
        severity=severity,
        check_id=check_id,
        file=file,
        category=category,
    )
    return f"SELECT * FROM findings WHERE {where}", params  # nosec B608


def _apply_run_fields(run: RunRecord, updates: dict[str, object | None]) -> None:
    for attr, value in updates.items():
        if value is not None:
            setattr(run, attr, value)


def _mark_run_finished(run: RunRecord) -> None:
    finished_at = utc_now()
    run.finished_at = finished_at
    run.duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)


def _dt_to_iso(value: datetime) -> str:
    return value.isoformat()


def _dt_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    summary = None
    if row["summary_json"]:
        summary = RunSummaryRecord.model_validate_json(row["summary_json"])
    return RunRecord(
        id=row["id"],
        branch=row["branch"],
        suite_id=row["suite_id"],
        status=RunStatus(row["status"]),
        started_at=_dt_from_iso(row["started_at"]),
        finished_at=_dt_from_iso(row["finished_at"]) if row["finished_at"] else None,
        duration_ms=row["duration_ms"],
        worktree_path=row["worktree_path"],
        error_message=row["error_message"],
        current_check_id=row["current_check_id"],
        checks_completed=row["checks_completed"],
        checks_total=row["checks_total"],
        summary=summary,
    )


def _row_to_finding(row: sqlite3.Row) -> FindingRecord:
    keys = set(row.keys())
    category_raw = row["category"] if "category" in keys and row["category"] else "code"
    return FindingRecord(
        id=row["id"],
        run_id=row["run_id"],
        check_id=row["check_id"],
        tool_id=row["tool_id"],
        rule_id=row["rule_id"],
        severity=row["severity"],
        message=row["message"],
        file=row["file"],
        line=row["line"],
        column=row["column_num"],
        docs_url=row["docs_url"],
        suggested_commands=json.loads(row["suggested_commands_json"]),
        category=FindingCategory(category_raw),
    )
