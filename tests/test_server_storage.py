from pathlib import Path

from shipgate.server.models import FindingRecord, RunStatus, RunSummaryRecord
from shipgate.server.storage.sqlite import SqliteStorage


def test_create_and_get_run(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="python-quality")
    assert run.status == RunStatus.QUEUED
    assert storage.get_run(run.id) is not None


def test_replace_findings_and_summary(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    storage.replace_findings(
        run.id,
        [
            FindingRecord(
                id="f1",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message="line too long",
                file="a.py",
                line=1,
                column=None,
                docs_url=None,
                suggested_commands=[],
            )
        ],
    )
    summary = RunSummaryRecord(finding_count=1, by_severity={"error": 1}, by_check_id={"ruff.lint": 1})
    updated = storage.update_run(run.id, status=RunStatus.SUCCEEDED, finished=True, summary=summary)
    assert updated.summary is not None
    assert updated.summary.finding_count == 1
    assert len(storage.list_findings(run.id)) == 1


def test_list_findings_file_filter_matches_substring(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    run = storage.create_run(branch="main", suite_id="all")
    storage.replace_findings(
        run.id,
        [
            FindingRecord(
                id="f1",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message="a",
                file="src/pkg/a.py",
                line=1,
            ),
            FindingRecord(
                id="f2",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message="b",
                file="tests/test_a.py",
                line=1,
            ),
        ],
    )
    matches = storage.list_findings(run.id, file="pkg")
    assert len(matches) == 1
    assert matches[0].file == "src/pkg/a.py"


def test_previous_completed_run_and_prune(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    first = storage.create_run(branch="main", suite_id="all")
    storage.update_run(first.id, status=RunStatus.SUCCEEDED, finished=True)
    second = storage.create_run(branch="main", suite_id="all")
    storage.update_run(second.id, status=RunStatus.SUCCEEDED, finished=True)
    prev = storage.previous_completed_run(branch="main", before_run_id=second.id)
    assert prev is not None and prev.id == first.id
    for _ in range(55):
        r = storage.create_run(branch="main", suite_id="all")
        storage.update_run(r.id, status=RunStatus.SUCCEEDED, finished=True)
    deleted = storage.prune_old_runs(keep=50)
    assert deleted >= 5
    assert len(storage.list_runs(limit=100)) == 50
