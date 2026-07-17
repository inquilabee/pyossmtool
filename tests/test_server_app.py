import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shipgate.models import CheckResult, utc_now
from shipgate.server.app import create_app
from shipgate.server.models import RunRecord, RunStatus
from shipgate.server.requirements import acknowledge
from shipgate.server.storage.sqlite import SqliteStorage


def test_health(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.get("/health").json() == {"ok": True}


def test_static_assets_served(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    overview = client.get("/")
    assert overview.status_code == 200
    assert b"cdn.tailwindcss.com" in overview.content


def test_overview_empty(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert b"No runs yet" in r.content or b"no runs" in r.content.lower()


def test_runs_list_empty(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    r = client.get("/runs")
    assert r.status_code == 200
    assert b"No runs yet" in r.content


def test_new_run_requires_acknowledge(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    r = client.post(
        "/runs/new",
        data={"branch": "main", "suite_id": "all"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/runs/new?")
    assert "acknowledge" in location.lower()


def test_new_run_with_acknowledge_redirects(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    fake_run = RunRecord(
        id="abc123def456",
        branch="main",
        suite_id="all",
        status=RunStatus.QUEUED,
        started_at=utc_now(),
    )
    app.state.orchestrator.start_run = MagicMock(return_value=fake_run)
    client = TestClient(app)
    r = client.post(
        "/runs/new",
        data={
            "branch": "main",
            "suite_id": "all",
            "acknowledge_requirements": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/?run_id={fake_run.id}"
    app.state.orchestrator.start_run.assert_called_once_with("main", "all")


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=True, capture_output=True)


def test_new_run_same_branch_completes_without_worktree_error(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    acknowledge(primary)

    app = create_app(primary)
    storage: SqliteStorage = app.state.storage
    client = TestClient(app)

    with (
        patch("shipgate.server.orchestrator.Installer") as installer_cls,
        patch("shipgate.server.orchestrator.Runner") as runner_cls,
    ):
        installer_cls.return_value.install_suite.return_value = None
        runner_cls.return_value.run_check.return_value = CheckResult(check_id="ruff.lint", passed=True)

        r = client.post(
            "/runs/new",
            data={
                "branch": "main",
                "suite_id": "python-quality",
                "acknowledge_requirements": "1",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        run_id = r.headers["location"].split("run_id=", 1)[1]
        assert app.state.orchestrator.wait(timeout=5) is True

    finished = storage.get_run(run_id)
    assert finished is not None
    assert finished.checks_total > 0
    assert finished.status == RunStatus.SUCCEEDED
    assert finished.worktree_path == str(primary.resolve())
    assert "worktree" not in (finished.error_message or "").lower()


def test_progress_unknown_run_404(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    r = client.get("/partials/runs/missing-run-id/progress")
    assert r.status_code == 404


def test_findings_page_smoke(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    run = storage.create_run(branch="main", suite_id="all")
    client = TestClient(app)
    r = client.get(f"/runs/{run.id}/findings")
    assert r.status_code == 200
    assert b"Findings" in r.content
    assert run.id[:8].encode() in r.content


def test_findings_page_omits_remediation(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    run = storage.create_run(branch="main", suite_id="all")
    storage.replace_findings(
        run.id,
        [
            FindingRecord(
                id="f1",
                run_id=run.id,
                check_id="mutmut.run",
                tool_id="mutmut",
                rule_id="mutmut",
                severity="error",
                message="ModuleNotFoundError: No module named 'typer'",
                file=None,
                line=None,
                column=None,
                docs_url="https://mutmut.readthedocs.io/",
                suggested_commands=["mutmut run", "mutmut results"],
                category=FindingCategory.TOOL,
            ),
            FindingRecord(
                id="f2",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message="line too long",
                file="a.py",
                line=1,
                column=None,
                docs_url="https://docs.astral.sh/ruff/",
                suggested_commands=["ruff check --fix a.py"],
                category=FindingCategory.CODE,
            ),
        ],
    )
    client = TestClient(app)
    r = client.get(f"/runs/{run.id}/findings")
    assert r.status_code == 200
    assert b"Code findings" in r.content
    assert b"Tools that could not run" in r.content
    assert b"no location" not in r.content
    assert b"ModuleNotFoundError: No module named &#39;typer&#39;" in r.content
    assert b"line too long" in r.content
    assert b"Remediation" not in r.content
    assert b"Documentation" not in r.content
    assert b"Suggested commands" not in r.content
    assert b"https://docs.astral.sh/ruff/" not in r.content
    assert b"ruff check --fix a.py" not in r.content
    assert b"mutmut.readthedocs.io" not in r.content
    assert b"mutmut results" not in r.content
    assert b'<select id="check_id"' in r.content
    assert b'<option value="mutmut.run"' in r.content
    assert b'type="text" name="check_id"' not in r.content


def test_overview_drill_down_links(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord, RunSummaryRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
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
                file="src/a.py",
                line=1,
                category=FindingCategory.CODE,
            ),
        ],
    )
    storage.update_run(
        run.id,
        status=RunStatus.SUCCEEDED,
        finished=True,
        summary=RunSummaryRecord(
            finding_count=1,
            by_severity={"error": 1},
            by_check_id={"ruff.lint": 1},
        ),
    )
    client = TestClient(app)
    r = client.get(f"/?run_id={run.id}")
    assert r.status_code == 200
    assert f"/runs/{run.id}/findings?severity=error".encode() in r.content
    assert f"/runs/{run.id}/findings?check_id=ruff.lint".encode() in r.content
    assert f"/runs/{run.id}/findings?file=src%2Fa.py".encode() in r.content or (b"file=src/a.py" in r.content)


def test_findings_pagination(tmp_path: Path) -> None:
    from shipgate.server.app import FINDINGS_PAGE_SIZE
    from shipgate.server.models import FindingCategory, FindingRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    run = storage.create_run(branch="main", suite_id="all")
    storage.replace_findings(
        run.id,
        [
            FindingRecord(
                id=f"f{i}",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message=f"line {i}",
                file=f"a{i}.py",
                line=1,
                category=FindingCategory.CODE,
            )
            for i in range(FINDINGS_PAGE_SIZE + 3)
        ],
    )
    client = TestClient(app)
    page1 = client.get(f"/runs/{run.id}/findings")
    assert page1.status_code == 200
    assert b"Showing 1" in page1.content
    assert b"of 53" in page1.content
    assert b"page=2" in page1.content
    assert b"Next" in page1.content
    page2 = client.get(f"/runs/{run.id}/findings?page=2")
    assert page2.status_code == 200
    assert b"Showing 51" in page2.content
    assert b"of 53" in page2.content
    assert b"Previous" in page2.content


def test_overview_shows_tool_failures_table(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord, RunSummaryRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
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
                category=FindingCategory.CODE,
            ),
            FindingRecord(
                id="f2",
                run_id=run.id,
                check_id="mutmut.run",
                tool_id="mutmut",
                rule_id="setup",
                severity="error",
                message="Failed to install mutmut",
                category=FindingCategory.TOOL,
            ),
        ],
    )
    storage.update_run(
        run.id,
        status=RunStatus.SUCCEEDED,
        finished=True,
        summary=RunSummaryRecord(
            finding_count=1,
            tool_failure_count=1,
            by_severity={"error": 1},
            by_check_id={"ruff.lint": 1},
        ),
    )
    client = TestClient(app)
    r = client.get(f"/?run_id={run.id}")
    assert r.status_code == 200
    assert b"Tools that could not run" in r.content
    assert b"Failed to install mutmut" in r.content
    assert b"Tool failures" in r.content


def test_tool_docs_page_lists_catalog_links(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    r = client.get("/tools")
    assert r.status_code == 200
    assert b"Tool docs" in r.content
    assert b"ruff" in r.content
    assert b"Open docs" in r.content
    assert b"Version" in r.content
    assert b"github.com/inquilabee/shipgate" in r.content


def test_pages_include_footer_with_github_link(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    for path in ("/", "/tools", "/runs"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"github.com/inquilabee/shipgate" in response.content
        assert b"shipgate" in response.content


def test_findings_page_shows_source_context(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("\n".join(f"line {index}" for index in range(1, 11)) + "\n", encoding="utf-8")

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
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
                file="src/app.py",
                line=5,
                category=FindingCategory.CODE,
            ),
        ],
    )
    client = TestClient(app)
    response = client.get(f"/runs/{run.id}/findings")
    assert response.status_code == 200
    assert b"finding-group" in response.content
    assert b"finding-summary" in response.content
    assert b"snippet-line-mark" in response.content
    assert b"snippet-code" in response.content
    assert b"line 5" in response.content


def test_findings_page_shows_tool_failure_message_snippet(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    run = storage.create_run(branch="main", suite_id="all")
    storage.replace_findings(
        run.id,
        [
            FindingRecord(
                id="tool1",
                run_id=run.id,
                check_id="mutmut.run",
                tool_id="mutmut",
                rule_id="mutmut",
                severity="error",
                message="FAILED tests/test_cli.py\nAssertionError: boom\nrunner returned 1",
                category=FindingCategory.TOOL,
            ),
        ],
    )
    client = TestClient(app)
    response = client.get(f"/runs/{run.id}/findings")
    assert response.status_code == 200
    assert b"Tools that could not run" in response.content
    assert b"finding-detail hidden" in response.content
    assert b"FAILED tests/test_cli.py" in response.content
    assert b"AssertionError: boom" in response.content


def test_findings_path_search_matches_substring(tmp_path: Path) -> None:
    from shipgate.server.models import FindingCategory, FindingRecord

    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
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
                file="src/deep/module.py",
                line=1,
                category=FindingCategory.CODE,
            ),
            FindingRecord(
                id="f2",
                run_id=run.id,
                check_id="ruff.lint",
                tool_id="ruff",
                rule_id="E501",
                severity="error",
                message="b",
                file="tests/test_x.py",
                line=1,
                category=FindingCategory.CODE,
            ),
        ],
    )
    client = TestClient(app)
    response = client.get(f"/runs/{run.id}/findings?file=deep")
    assert response.status_code == 200
    assert b"src/deep/module.py" in response.content
    assert b"tests/test_x.py" not in response.content


def test_overview_shows_failed_error_message(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    run = storage.create_run(branch="main", suite_id="all")
    storage.update_run(
        run.id,
        status=RunStatus.FAILED,
        error_message="boom: worktree failed",
        finished=True,
    )
    client = TestClient(app)
    r = client.get(f"/?run_id={run.id}")
    assert r.status_code == 200
    assert b"boom: worktree failed" in r.content
    assert b"No runs yet" not in r.content

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert b"boom: worktree failed" in runs.content


def test_overview_unknown_run_id(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    storage: SqliteStorage = app.state.storage
    existing = storage.create_run(branch="main", suite_id="all")
    client = TestClient(app)
    r = client.get("/?run_id=does-not-exist")
    assert r.status_code == 200
    assert b"Run not found" in r.content
    assert b"No runs yet" not in r.content
    assert existing.id.encode() in r.content
