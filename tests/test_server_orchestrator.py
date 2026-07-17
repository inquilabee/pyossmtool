import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shipgate.models import CheckMode, CheckResult, EnvMode, ProjectConfig, SuiteCheckRef, SuiteDef
from shipgate.server.models import RunStatus
from shipgate.server.orchestrator import OrchestratorError, RunOrchestrator
from shipgate.server.requirements import acknowledge, is_acknowledged
from shipgate.server.storage.sqlite import SqliteStorage


def test_requirements_ack(tmp_path: Path) -> None:
    assert is_acknowledged(tmp_path) is False
    acknowledge(tmp_path)
    assert is_acknowledged(tmp_path) is True


def test_start_run_requires_ack(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    orch = RunOrchestrator(tmp_path, storage, registry=MagicMock())
    with pytest.raises(OrchestratorError, match="acknowledge"):
        orch.start_run("main", "all")


def test_start_run_succeeds_with_mocks(tmp_path: Path) -> None:
    acknowledge(tmp_path)
    storage = SqliteStorage(tmp_path / "db.sqlite")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    primary = tmp_path.resolve()

    suite = SuiteDef(
        id="all",
        name="All",
        description="all checks",
        checks=[SuiteCheckRef(id="ruff.lint"), SuiteCheckRef(id="pytest.test")],
    )
    ruff_check = MagicMock()
    ruff_check.mode = CheckMode.CHECK
    ruff_check.tool = "ruff"
    pytest_check = MagicMock()
    pytest_check.mode = CheckMode.CHECK
    pytest_check.tool = "pytest"

    registry = MagicMock()
    registry.get_suite.return_value = suite
    registry.get_check.side_effect = lambda check_id: {
        "ruff.lint": ruff_check,
        "pytest.test": pytest_check,
    }[check_id]
    registry.load_project_config.return_value = ProjectConfig(suite="all", env=EnvMode.AUTO)

    runner = MagicMock()
    runner.run_check.side_effect = [
        CheckResult(check_id="ruff.lint", passed=True),
        CheckResult(check_id="pytest.test", passed=True),
    ]

    with (
        patch("shipgate.server.orchestrator.WorktreeManager") as wt_cls,
        patch("shipgate.server.orchestrator.Installer") as installer_cls,
        patch("shipgate.server.orchestrator.Runner", return_value=runner) as runner_cls,
    ):
        wt_cls.return_value.resolve_run_root.return_value = worktree
        installer_cls.return_value.install_suite.return_value = None

        orch = RunOrchestrator(tmp_path, storage, registry=registry)
        run = orch.start_run("main", "all")
        assert orch.wait(timeout=2) is True

    finished = storage.get_run(run.id)
    assert finished is not None
    assert finished.status == RunStatus.SUCCEEDED
    assert orch.active_run_id() is None
    installer_cls.assert_called_once()
    assert installer_cls.call_args.kwargs["project_root"] == primary
    assert installer_cls.call_args.kwargs["tools_root"] == primary
    installer_cls.return_value.install_suite.assert_called_once_with("all")
    runner_cls.assert_called_once()
    assert runner_cls.call_args.kwargs["project_root"] == worktree
    assert runner_cls.call_args.kwargs["tools_root"] == primary
    wt_cls.return_value.resolve_run_root.assert_called_once_with("main")
    assert runner.run_check.call_count == 2
    assert runner.run_check.call_args_list[0].kwargs["env_mode"] == EnvMode.MANAGED
    assert runner.run_check.call_args_list[1].kwargs["env_mode"] == EnvMode.PROJECT


def test_start_run_rejects_when_already_active(tmp_path: Path) -> None:
    acknowledge(tmp_path)
    storage = SqliteStorage(tmp_path / "db.sqlite")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    gate = threading.Event()

    def blocked_resolve_run_root(_branch: str) -> Path:
        assert gate.wait(timeout=5)
        return worktree

    with (
        patch("shipgate.server.orchestrator.WorktreeManager") as wt_cls,
        patch("shipgate.server.orchestrator.Installer") as installer_cls,
        patch("shipgate.server.orchestrator.Runner"),
    ):
        wt_cls.return_value.resolve_run_root.side_effect = blocked_resolve_run_root
        installer_cls.return_value.install_suite.return_value = None

        orch = RunOrchestrator(tmp_path, storage, registry=MagicMock())
        run = orch.start_run("main", "all")
        with pytest.raises(OrchestratorError, match="already|active"):
            orch.start_run("main", "all")
        gate.set()
        assert orch.wait(timeout=2) is True

    finished = storage.get_run(run.id)
    assert finished is not None
    assert orch.active_run_id() is None


def test_init_fails_stale_queued_or_running_runs(tmp_path: Path) -> None:
    storage = SqliteStorage(tmp_path / "db.sqlite")
    stale = storage.create_run(branch="main", suite_id="all")
    storage.update_run(stale.id, status=RunStatus.RUNNING)

    RunOrchestrator(tmp_path, storage, registry=MagicMock())

    refreshed = storage.get_run(stale.id)
    assert refreshed is not None
    assert refreshed.status == RunStatus.FAILED
    assert refreshed.error_message is not None
    assert "stale" in refreshed.error_message or "interrupted" in refreshed.error_message
