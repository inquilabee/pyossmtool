import re
import subprocess
from pathlib import Path

import pytest

from shipgate.server.worktree import WorktreeError, WorktreeManager, safe_branch_name


def _git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True)


def test_resolve_run_root_returns_primary_when_branch_matches(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    subprocess.run(["git", "branch", "-M", "main"], cwd=primary, check=True, capture_output=True)
    mgr = WorktreeManager(primary)
    assert mgr.resolve_run_root("main") == primary.resolve()


def test_ensure_worktree_creates_branch_checkout(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    subprocess.run(["git", "branch", "feature/x"], cwd=primary, check=True, capture_output=True)
    mgr = WorktreeManager(primary)
    wt = mgr.ensure_worktree("feature/x")
    assert wt.is_dir()
    assert (wt / "README").exists()
    # idempotent
    assert mgr.ensure_worktree("feature/x") == wt


def test_not_a_git_repo(tmp_path: Path) -> None:
    mgr = WorktreeManager(tmp_path)
    with pytest.raises(WorktreeError):
        mgr.list_branches()


def test_safe_branch_name_avoids_slash_collision() -> None:
    """feature/x and feature__x must not share a directory name."""
    a = safe_branch_name("feature/x")
    b = safe_branch_name("feature__x")
    assert a != b
    assert a
    assert b
    assert "-" not in a
    assert "-" not in b
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", a)
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", b)


def test_safe_branch_name_is_valid_python_identifier() -> None:
    for branch in ("main", "feature/x", "3.14", "@@@", "日本語"):
        name = safe_branch_name(branch)
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name), name
        assert "-" not in name


def test_safe_branch_name_unicode_or_special_is_nonempty() -> None:
    name = safe_branch_name("日本語ブランチ")
    assert name
    assert "/" not in name
    assert "\\" not in name

    special = safe_branch_name("@@@")
    assert special
    assert special == safe_branch_name("@@@")  # stable


def test_safe_branch_name_stable_for_same_branch() -> None:
    assert safe_branch_name("feature/x") == safe_branch_name("feature/x")


def test_collision_branches_get_different_worktree_paths(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    subprocess.run(["git", "branch", "feature/x"], cwd=primary, check=True, capture_output=True)
    subprocess.run(["git", "branch", "feature__x"], cwd=primary, check=True, capture_output=True)
    mgr = WorktreeManager(primary)
    wt_slash = mgr.ensure_worktree("feature/x")
    wt_underscores = mgr.ensure_worktree("feature__x")
    assert wt_slash != wt_underscores
    assert wt_slash.parent == primary / ".shipgate" / "worktrees"
    assert wt_underscores.parent == primary / ".shipgate" / "worktrees"


def test_unicode_branch_gets_nonempty_worktree_path(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    branch = "日本語"
    created = subprocess.run(
        ["git", "branch", branch],
        cwd=primary,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        # Fall back to unit-level guarantee when the filesystem/git rejects the name.
        name = safe_branch_name(branch)
        assert name
        path = primary / ".shipgate" / "worktrees" / name
        assert path.name
        return

    mgr = WorktreeManager(primary)
    wt = mgr.ensure_worktree(branch)
    assert wt.is_dir()
    assert wt.name
    assert wt.parent == (primary / ".shipgate" / "worktrees").resolve()
    assert wt == mgr.ensure_worktree(branch)


def test_reuse_raises_when_worktree_branch_mismatches(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git_repo(primary)
    subprocess.run(["git", "branch", "feature/a"], cwd=primary, check=True, capture_output=True)
    subprocess.run(["git", "branch", "feature/b"], cwd=primary, check=True, capture_output=True)
    mgr = WorktreeManager(primary)
    wt = mgr.ensure_worktree("feature/a")

    # Simulate a path collision reuse by pointing another branch name at the same path
    # via monkeypatching safe_branch_name equivalence — instead, force-checkout wrong branch.
    subprocess.run(
        ["git", "-C", str(wt), "checkout", "feature/b"],
        check=True,
        capture_output=True,
    )
    with pytest.raises(WorktreeError, match="branch mismatch|expected"):
        mgr.ensure_worktree("feature/a")
