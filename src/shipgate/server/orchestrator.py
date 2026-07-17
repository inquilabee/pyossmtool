"""Background suite-run orchestration for the report server."""

from __future__ import annotations

import threading
from pathlib import Path

from shipgate.installer import Installer
from shipgate.models import (
    CheckMode,
    CheckResult,
    EnvMode,
    ProjectConfig,
    SuiteCheckRef,
    SuiteDef,
    SuiteResult,
)
from shipgate.registry import Registry
from shipgate.runner import Runner
from shipgate.server.ingest import ingest_suite_result
from shipgate.server.models import RunRecord, RunStatus
from shipgate.server.requirements import is_acknowledged
from shipgate.server.storage.base import MAX_RUNS, Storage
from shipgate.server.worktree import WorktreeError, WorktreeManager
from shipgate.target_expand import resolve_suite_target

# Tools that must import the project under test (need the user project venv + src on PYTHONPATH).
_PROJECT_ENV_TOOL_IDS = frozenset({"pytest", "mutmut"})


class OrchestratorError(Exception):
    """Raised when a run cannot be started."""


class RunOrchestrator:
    """Queue and execute one suite run at a time against a git worktree."""

    def __init__(self, primary_root: Path, storage: Storage, registry: Registry) -> None:
        self._primary_root = Path(primary_root).resolve()
        self._storage = storage
        self._registry = registry
        self._lock = threading.Lock()
        self._active_run_id: str | None = None
        self._done = threading.Event()
        self._done.set()
        self._fail_stale_runs()

    def active_run_id(self) -> str | None:
        return self._active_run_id

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the background run finishes. Returns False on timeout."""
        return self._done.wait(timeout)

    def start_run(self, branch: str, suite_id: str) -> RunRecord:
        if not is_acknowledged(self._primary_root):
            raise OrchestratorError("acknowledge requirements before starting a run")

        with self._lock:
            if self._active_run_id is not None or self._has_active_run():
                raise OrchestratorError("a run is already active")

            run = self._storage.create_run(branch=branch, suite_id=suite_id)
            self._active_run_id = run.id
            self._done.clear()
            thread = threading.Thread(
                target=self._execute_run,
                args=(run.id, branch, suite_id),
                daemon=True,
                name=f"shipgate-run-{run.id}",
            )
            thread.start()
            return run

    def _fail_stale_runs(self) -> None:
        """Mark queued/running storage rows failed so a crash cannot lock out new starts."""
        for run in self._storage.list_runs(limit=MAX_RUNS):
            if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
                self._storage.update_run(
                    run.id,
                    status=RunStatus.FAILED,
                    error_message="run interrupted (stale after process restart)",
                    finished=True,
                )

    def _has_active_run(self) -> bool:
        for run in self._storage.list_runs(limit=MAX_RUNS):
            if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
                return True
        return False

    def _execute_run(self, run_id: str, branch: str, suite_id: str) -> None:
        try:
            self._perform_run(run_id, branch, suite_id)
        except Exception as exc:
            self._persist_failure(run_id, exc)
        finally:
            self._finish_run(run_id)

    def _perform_run(self, run_id: str, branch: str, suite_id: str) -> None:
        worktree = self._resolve_worktree(branch)
        self._storage.update_run(run_id, status=RunStatus.RUNNING, worktree_path=str(worktree))
        Installer(
            self._registry,
            project_root=self._primary_root,
            tools_root=self._primary_root,
        ).install_suite(suite_id)
        runner = Runner(self._registry, project_root=worktree, tools_root=self._primary_root)
        project_config = self._force_managed_config(self._registry.load_project_config(worktree))
        suite_result = self._run_checks(runner, suite_id, project_config, run_id)
        summary = ingest_suite_result(self._storage, run_id, suite_result, worktree)
        status = RunStatus.SUCCEEDED if suite_result.passed else RunStatus.FAILED
        self._storage.update_run(run_id, status=status, finished=True, summary=summary)
        self._storage.prune_old_runs(keep=MAX_RUNS)

    def _resolve_worktree(self, branch: str) -> Path:
        try:
            return WorktreeManager(self._primary_root).resolve_run_root(branch)
        except WorktreeError as exc:
            raise OrchestratorError(f"worktree failed: {exc}") from exc

    def _persist_failure(self, run_id: str, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        try:
            self._storage.update_run(run_id, status=RunStatus.FAILED, error_message=message, finished=True)
        except Exception as update_exc:
            update_message = str(update_exc) or update_exc.__class__.__name__
            raise OrchestratorError(f"{message}; failed to persist status: {update_message}") from update_exc

    def _finish_run(self, run_id: str) -> None:
        with self._lock:
            if self._active_run_id == run_id:
                self._active_run_id = None
            self._done.set()

    def _force_managed_config(self, project_config: ProjectConfig | None) -> ProjectConfig | None:
        if project_config is None:
            return None
        return project_config.model_copy(update={"env": EnvMode.MANAGED})

    def _run_checks(
        self,
        runner: Runner,
        suite_id: str,
        project_config: ProjectConfig | None,
        run_id: str,
    ) -> SuiteResult:
        suite = self._registry.get_suite(suite_id)
        check_refs = self._checks_to_run(project_config, suite)
        self._storage.update_run(run_id, checks_total=len(check_refs), checks_completed=0)

        results: list[CheckResult] = []
        for index, check_ref in enumerate(check_refs):
            results.append(self._run_single_check(runner, check_ref, suite, suite_id, project_config, run_id))
            self._storage.update_run(run_id, checks_completed=index + 1)

        return SuiteResult(
            suite_id=suite_id,
            passed=all(result.passed for result in results),
            results=results,
        )

    def _checks_to_run(self, project_config: ProjectConfig | None, suite: SuiteDef) -> list[SuiteCheckRef]:
        check_refs = project_config.checks if project_config and project_config.checks else suite.checks
        return [ref for ref in check_refs if self._registry.get_check(ref.id).mode == CheckMode.CHECK]

    def _run_single_check(
        self,
        runner: Runner,
        check_ref: SuiteCheckRef,
        suite: SuiteDef,
        suite_id: str,
        project_config: ProjectConfig | None,
        run_id: str,
    ) -> CheckResult:
        self._storage.update_run(run_id, current_check_id=check_ref.id)
        target = resolve_suite_target(check_ref, suite, project_config)
        check = self._registry.get_check(check_ref.id)
        env_mode = EnvMode.PROJECT if check.tool in _PROJECT_ENV_TOOL_IDS else EnvMode.MANAGED
        return runner.run_check(
            check_ref.id,
            target=target,
            suite_id=suite_id,
            env_mode=env_mode,
            project_config=project_config,
            suite=suite,
            check_ref=check_ref,
        )
