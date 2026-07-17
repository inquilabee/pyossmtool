"""FastAPI report UI for local suite runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shipgate import __version__ as shipgate_version
from shipgate.constants import PROJECT_SERVER_DIR, SERVER_DB_FILENAME
from shipgate.paths import normalize_finding_path
from shipgate.registry import Registry
from shipgate.server.finding_context import message_contexts, source_contexts
from shipgate.server.models import FindingCategory, FindingRecord, RunRecord, RunSummaryRecord
from shipgate.server.orchestrator import OrchestratorError, RunOrchestrator
from shipgate.server.requirements import acknowledge, is_acknowledged
from shipgate.server.storage.sqlite import SqliteStorage
from shipgate.server.tool_versions import tool_docs_rows
from shipgate.server.worktree import WorktreeError, WorktreeManager

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
FINDINGS_PAGE_SIZE = 50
GITHUB_REPO_URL = "https://github.com/inquilabee/shipgate"
REQUIREMENTS_TEXT = (
    "This run uses a separate git worktree under `.shipgate/worktrees/` so your current "
    "checkout is not switched. Most quality tools run from shipgate's managed environment under "
    "`.shipgate/tools/`. Pytest and mutmut use the project environment that started the server "
    "(active VIRTUAL_ENV / current interpreter, or a conventional `.venv`), with the worktree on "
    "PYTHONPATH so tests can import your package. Disk space is used under `.shipgate/` for "
    "worktrees, tools, and the local SQLite database."
)


def create_app(primary_root: Path) -> FastAPI:
    primary = Path(primary_root).resolve()
    storage = SqliteStorage(primary / PROJECT_SERVER_DIR / SERVER_DB_FILENAME)
    registry = Registry(project_root=primary)
    orchestrator = RunOrchestrator(primary, storage, registry)
    worktrees = WorktreeManager(primary)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    cast("dict[str, object]", templates.env.globals).update(
        {
            "github_repo_url": GITHUB_REPO_URL,
            "shipgate_version": shipgate_version,
        },
    )

    app = FastAPI(title="shipgate report")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.primary_root = primary
    app.state.storage = storage
    app.state.registry = registry
    app.state.orchestrator = orchestrator
    app.state.worktrees = worktrees
    app.state.templates = templates
    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, run_id: str | None = None) -> HTMLResponse:
        storage: SqliteStorage = request.app.state.storage
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(request, "overview.html", _overview_context(request, storage, run_id))

    @app.get("/runs", response_class=HTMLResponse)
    def runs_list(request: Request) -> HTMLResponse:
        storage: SqliteStorage = request.app.state.storage
        templates: Jinja2Templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "runs.html",
            {"request": request, "runs": storage.list_runs(limit=50)},
        )

    @app.get("/runs/new", response_class=HTMLResponse)
    def new_run_form(request: Request, error: str | None = None) -> HTMLResponse:
        return request.app.state.templates.TemplateResponse(
            request,
            "new_run.html",
            _new_run_context(request, error),
        )

    @app.post("/runs/new")
    def new_run_submit(
        request: Request,
        branch: str = Form(...),
        suite_id: str = Form(...),
        acknowledge_requirements: str | None = Form(None),
    ) -> RedirectResponse:
        return _start_new_run(
            request.app.state.primary_root,
            request.app.state.orchestrator,
            branch,
            suite_id,
            acknowledge_requirements,
        )

    @app.get("/runs/{run_id}/findings", response_class=HTMLResponse)
    def findings_page(
        request: Request,
        run_id: str,
        severity: str | None = Query(None),
        check_id: str | None = Query(None),
        file: str | None = Query(None),
        page: int = Query(1, ge=1),
    ) -> HTMLResponse:
        return _findings_response(request, run_id, severity, check_id, file, page)

    @app.get("/partials/runs/{run_id}/progress", response_class=HTMLResponse)
    def run_progress(request: Request, run_id: str) -> HTMLResponse:
        run = request.app.state.storage.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/run_progress.html",
            {"request": request, "run": run},
        )

    @app.get("/tools", response_class=HTMLResponse)
    def tool_docs(request: Request) -> HTMLResponse:
        registry: Registry = request.app.state.registry
        primary: Path = request.app.state.primary_root
        tools = sorted(registry.tools.values(), key=lambda tool: tool.id)
        return request.app.state.templates.TemplateResponse(
            request,
            "tools.html",
            {"request": request, "tools": tool_docs_rows(tools, primary)},
        )


def _overview_context(request: Request, storage: SqliteStorage, run_id: str | None) -> dict[str, Any]:
    run, run_missing = _resolve_overview_run(storage, run_id)
    latest = storage.list_runs(limit=1)
    context: dict[str, Any] = {
        "request": request,
        "run": run,
        "run_missing": run_missing,
        "latest_run": latest[0] if latest else None,
        "previous": None,
        "deltas": None,
        "hotspots": [],
        "by_check": [],
        "tool_failures": [],
    }
    if run is None:
        return context
    previous = storage.previous_completed_run(branch=run.branch, before_run_id=run.id)
    context["previous"] = previous
    context["deltas"] = _severity_deltas(run.summary, previous.summary if previous else None)
    code_findings = storage.list_findings(run.id, category=FindingCategory.CODE)
    context["hotspots"] = _file_hotspots(code_findings)
    context["by_check"] = _by_check_rows(run.summary)
    context["tool_failures"] = storage.list_findings(run.id, category=FindingCategory.TOOL)
    return context


def _new_run_context(request: Request, error: str | None) -> dict[str, Any]:
    primary: Path = request.app.state.primary_root
    registry: Registry = request.app.state.registry
    worktrees: WorktreeManager = request.app.state.worktrees
    return {
        "request": request,
        "branches": _safe_branches(worktrees),
        "suites": sorted(registry.suites.keys()),
        "default_suite": _default_suite(registry, primary),
        "needs_ack": not is_acknowledged(primary),
        "requirements_text": REQUIREMENTS_TEXT,
        "error": error,
    }


def _start_new_run(
    primary: Path,
    orchestrator: RunOrchestrator,
    branch: str,
    suite_id: str,
    acknowledge_requirements: str | None,
) -> RedirectResponse:
    if not is_acknowledged(primary):
        if not acknowledge_requirements:
            return RedirectResponse(
                url="/runs/new?error=Please+acknowledge+the+requirements+before+starting",
                status_code=303,
            )
        acknowledge(primary)
    try:
        run = orchestrator.start_run(branch, suite_id)
    except OrchestratorError as exc:
        return RedirectResponse(url=f"/runs/new?error={_query_escape(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/?run_id={run.id}", status_code=303)


@dataclass
class _FindingsPage:
    total: int
    page: int
    total_pages: int
    offset: int
    page_size: int
    code_findings: list[FindingRecord]
    tool_failures: list[FindingRecord]
    showing_from: int
    showing_to: int


def _finding_filters(severity: str | None, check_id: str | None, file_filter: str | None) -> dict[str, str | None]:
    return {
        "severity": severity or None,
        "check_id": check_id or None,
        "file": file_filter,
    }


def _filter_display(filters: dict[str, str | None], file_filter: str | None) -> dict[str, str]:
    return {
        "severity": filters["severity"] or "",
        "check_id": filters["check_id"] or "",
        "file": file_filter or "",
    }


def _load_findings_page(
    storage: SqliteStorage,
    run_id: str,
    filters: dict[str, str | None],
    page: int,
) -> _FindingsPage:
    page_size = FINDINGS_PAGE_SIZE
    total = storage.count_findings(run_id, category=FindingCategory.CODE, **filters)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    code_findings = storage.list_findings(
        run_id,
        category=FindingCategory.CODE,
        limit=page_size,
        offset=offset,
        **filters,
    )
    tool_failures = storage.list_findings(
        run_id,
        category=FindingCategory.TOOL,
        check_id=filters["check_id"],
        severity=filters["severity"],
    )
    return _FindingsPage(
        total=total,
        page=page,
        total_pages=total_pages,
        offset=offset,
        page_size=page_size,
        code_findings=code_findings,
        tool_failures=tool_failures,
        showing_from=offset + 1 if total else 0,
        showing_to=offset + len(code_findings),
    )


def _findings_nav_urls(run_id: str, query: dict[str, str], page: _FindingsPage) -> tuple[str | None, str | None]:
    prev_url = _findings_page_url(run_id, query, page.page - 1) if page.page > 1 else None
    next_url = _findings_page_url(run_id, query, page.page + 1) if page.page < page.total_pages else None
    return prev_url, next_url


def _active_query(filters: dict[str, str | None], file_filter: str | None) -> dict[str, str]:
    return {k: v for k, v in _filter_display(filters, file_filter).items() if v}


def _page_message_contexts(page: _FindingsPage, source_ctx: dict[str, Any]) -> dict[str, Any]:
    extra = [finding for finding in page.code_findings if finding.id not in source_ctx]
    return message_contexts(page.tool_failures + extra)


def _findings_context(
    request: Request,
    run: RunRecord,
    storage: SqliteStorage,
    filters: dict[str, str | None],
    file_filter: str | None,
    page: _FindingsPage,
) -> dict[str, Any]:
    query = _active_query(filters, file_filter)
    project_root = Path(run.worktree_path) if run.worktree_path else request.app.state.primary_root
    source_ctx = source_contexts(project_root, page.code_findings)
    message_ctx = _page_message_contexts(page, source_ctx)
    prev_url, next_url = _findings_nav_urls(run.id, query, page)
    return {
        "request": request,
        "run": run,
        "findings": page.code_findings,
        "source_contexts": source_ctx,
        "message_contexts": message_ctx,
        "tool_failures": page.tool_failures,
        "check_options": _check_options_for_run(storage, run),
        **_filter_display(filters, file_filter),
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": page.total_pages,
        "showing_from": page.showing_from,
        "showing_to": page.showing_to,
        "prev_page_url": prev_url,
        "next_page_url": next_url,
    }


def _findings_response(
    request: Request,
    run_id: str,
    severity: str | None,
    check_id: str | None,
    file: str | None,
    page: int,
) -> HTMLResponse:
    storage: SqliteStorage = request.app.state.storage
    run = storage.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    file_filter = normalize_finding_path(file) if file else None
    filters = _finding_filters(severity, check_id, file_filter)
    page_data = _load_findings_page(storage, run_id, filters, page)
    context = _findings_context(request, run, storage, filters, file_filter, page_data)
    return request.app.state.templates.TemplateResponse(request, "findings.html", context)


def _findings_page_url(run_id: str, query: dict[str, str], page: int) -> str:
    params = dict(query)
    if page > 1:
        params["page"] = str(page)
    qs = urlencode(params)
    base = f"/runs/{run_id}/findings"
    return f"{base}?{qs}" if qs else base


def _summary_check_ids(run: RunRecord) -> set[str]:
    if not run.summary or not run.summary.by_check_id:
        return set()
    return {check_id for check_id, count in run.summary.by_check_id.items() if count > 0}


def _check_options_for_run(storage: SqliteStorage, run: RunRecord) -> list[str]:
    options = _summary_check_ids(run)
    for finding in storage.list_findings(run.id):
        options.add(finding.check_id)
    return sorted(options)


def _resolve_overview_run(storage: SqliteStorage, run_id: str | None) -> tuple[RunRecord | None, bool]:
    """Return (run, run_missing). run_missing is True when a specific id was requested but not found."""
    if run_id:
        run = storage.get_run(run_id)
        if run is None:
            return None, True
        return run, False
    runs = storage.list_runs(limit=1)
    return (runs[0] if runs else None), False


def _safe_branches(worktrees: WorktreeManager) -> list[str]:
    try:
        return worktrees.list_branches()
    except WorktreeError:
        return []


def _default_suite(registry: Registry, primary: Path) -> str:
    config = registry.load_project_config(primary)
    if config is not None and config.suite in registry.suites:
        return config.suite
    if "all" in registry.suites:
        return "all"
    return next(iter(sorted(registry.suites.keys())), "")


def _severity_deltas(
    current: RunSummaryRecord | None,
    previous: RunSummaryRecord | None,
) -> dict[str, int] | None:
    if current is None or previous is None:
        return None
    keys = ("error", "warning", "info")
    cur = current.by_severity
    prev = previous.by_severity
    return {
        "total": current.finding_count - previous.finding_count,
        **{key: cur.get(key, 0) - prev.get(key, 0) for key in keys},
    }


def _file_hotspots(findings: list[FindingRecord], *, limit: int = 10) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for finding in findings:
        if finding.file:
            counts[finding.file] += 1
    return [{"file": path, "count": count} for path, count in counts.most_common(limit)]


def _by_check_rows(summary: RunSummaryRecord | None) -> list[dict[str, Any]]:
    if summary is None:
        return []
    return [
        {"check_id": check_id, "count": count}
        for check_id, count in sorted(summary.by_check_id.items(), key=lambda item: (-item[1], item[0]))
        if count > 0
    ]


def _query_escape(value: str) -> str:
    return quote(value, safe="")
