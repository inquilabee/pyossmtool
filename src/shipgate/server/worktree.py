"""Git worktree management for isolated server suite runs."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from shipgate.constants import PROJECT_WORKTREES_DIR


class WorktreeError(Exception):
    """Raised when git or worktree operations fail."""


def _git_error(exc: subprocess.CalledProcessError, fallback: str) -> WorktreeError:
    detail = (exc.stderr or exc.stdout or str(exc)).strip()
    return WorktreeError(detail or fallback)


_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_]+")
_HASH_LEN = 12


def safe_branch_name(branch: str) -> str:
    """Return a unique worktree directory name that is a valid Python identifier.

    pydeps (and similar tools) treat the worktree basename as a module name when
    analyzing ``.``, so names must match ``[A-Za-z_][A-Za-z0-9_]*`` — no hyphens.
    """
    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:_HASH_LEN]
    replaced = branch.replace("/", "__")
    sanitized = _UNSAFE_CHARS.sub("_", replaced).strip("_")
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    if sanitized and sanitized[0].isdigit():
        sanitized = f"b_{sanitized}"
    if sanitized:
        return f"{sanitized}_{digest}"
    return f"wt_{digest}"


class WorktreeManager:
    """Create and reuse git worktrees under ``.shipgate/worktrees/``."""

    def __init__(self, primary_root: Path) -> None:
        self._primary_root = primary_root.resolve()

    def list_branches(self) -> list[str]:
        self._require_git_repo()
        result = self._run_git(["branch", "--format=%(refname:short)"])
        branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return branches

    def ensure_worktree(self, branch: str) -> Path:
        self._require_git_repo()
        target = (self._primary_root / PROJECT_WORKTREES_DIR / safe_branch_name(branch)).resolve()
        if target in self._worktree_paths():
            checked_out = self._checked_out_branch(target)
            if checked_out != branch:
                raise WorktreeError(f"worktree branch mismatch at {target}: expected {branch!r}, found {checked_out!r}")
            return target

        target.parent.mkdir(parents=True, exist_ok=True)
        self._run_git(["worktree", "add", str(target), branch])
        return target

    def resolve_run_root(self, branch: str) -> Path:
        """Use the primary checkout when the branch is already checked out there."""
        self._require_git_repo()
        current = self._current_branch()
        if current is not None and current == branch:
            return self._primary_root
        return self.ensure_worktree(branch)

    def _current_branch(self) -> str | None:
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        name = result.stdout.strip()
        if name == "HEAD":
            return None
        return name

    def _checked_out_branch(self, worktree_path: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(worktree_path), "rev-parse", "--abbrev-ref", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise _git_error(exc, f"failed to read branch at {worktree_path}") from exc
        except FileNotFoundError as exc:
            raise WorktreeError("git executable not found") from exc
        return result.stdout.strip()

    def _require_git_repo(self) -> None:
        try:
            result = self._run_git(["rev-parse", "--is-inside-work-tree"])
        except WorktreeError as exc:
            raise WorktreeError(f"Not a git repository: {self._primary_root}") from exc
        if result.stdout.strip() != "true":
            raise WorktreeError(f"Not a git repository: {self._primary_root}")

    def _worktree_paths(self) -> set[Path]:
        result = self._run_git(["worktree", "list", "--porcelain"])
        paths: set[Path] = set()
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                paths.add(Path(line[len("worktree ") :]).resolve())
        return paths

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._primary_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise _git_error(exc, f"git {' '.join(args)} failed") from exc
        except FileNotFoundError as exc:
            raise WorktreeError("git executable not found") from exc
