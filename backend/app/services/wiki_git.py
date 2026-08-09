"""Local git versioning for each Class's wiki directory.

Every Class has a wiki at ``data_dir/classes/{class_id}/wiki/``. That
directory is its own local git repository (no remote) so that every
wiki-modifying operation -- ingest, rebuild, remove, user edit -- can be
auto-committed and later inspected or reverted. If ``git`` isn't installed on
the host, every function here logs a warning and degrades to a no-op so the
rest of the app keeps working without version history.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger()

_GIT_AVAILABLE = shutil.which("git") is not None
_warned_missing_git = False


def _warn_git_missing() -> None:
    global _warned_missing_git
    if not _warned_missing_git:
        logger.warning("git_not_found", detail="wiki version history is disabled")
        _warned_missing_git = True


def wiki_dir(class_id: str) -> Path:
    """Return the wiki directory path for a Class, without creating it."""
    return settings.data_dir / "classes" / class_id / "wiki"


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def init_wiki_repo(class_id: str) -> Path:
    """Ensure the Class's wiki directory exists and is a git repository."""
    path = wiki_dir(class_id)
    path.mkdir(parents=True, exist_ok=True)

    if not _GIT_AVAILABLE:
        _warn_git_missing()
        return path

    if not (path / ".git").exists():
        result = _run_git(["init"], cwd=path)
        if result.returncode != 0:
            logger.warning("git_init_failed", class_id=class_id, stderr=result.stderr.strip())
            return path
        _run_git(["config", "user.name", "Hypatia"], cwd=path)
        _run_git(["config", "user.email", "hypatia@localhost"], cwd=path)
        logger.info("wiki_repo_initialized", class_id=class_id)

    return path


def commit_wiki_change(class_id: str, message: str) -> str | None:
    """Stage and commit all changes in a Class's wiki. Returns the new
    commit sha, or ``None`` if there was nothing to commit or git is
    unavailable."""
    if not _GIT_AVAILABLE:
        _warn_git_missing()
        return None

    path = init_wiki_repo(class_id)
    _run_git(["add", "-A"], cwd=path)

    status = _run_git(["status", "--porcelain"], cwd=path)
    if not status.stdout.strip():
        return None

    commit = _run_git(["commit", "-m", message], cwd=path)
    if commit.returncode != 0:
        logger.warning("wiki_commit_failed", class_id=class_id, stderr=commit.stderr.strip())
        return None

    sha = _run_git(["rev-parse", "HEAD"], cwd=path).stdout.strip()
    logger.info("wiki_committed", class_id=class_id, commit_sha=sha, message=message)
    return sha


def get_wiki_history(class_id: str, page_path: str | None = None) -> list[dict[str, str]]:
    """Return commit history for a Class's wiki, optionally scoped to a
    single page path (relative to the wiki root). Most recent first."""
    if not _GIT_AVAILABLE:
        _warn_git_missing()
        return []

    path = wiki_dir(class_id)
    if not (path / ".git").exists():
        return []

    separator = "\x1f"
    args = ["log", f"--pretty=format:%H{separator}%an{separator}%aI{separator}%s"]
    if page_path:
        args.extend(["--", page_path])

    result = _run_git(args, cwd=path)
    if result.returncode != 0 or not result.stdout.strip():
        return []

    history: list[dict[str, str]] = []
    for line in result.stdout.strip().splitlines():
        sha, author, date, message = line.split(separator, 3)
        history.append({"sha": sha, "author": author, "date": date, "message": message})
    return history


def revert_wiki_to(class_id: str, commit_sha: str) -> str | None:
    """Restore the wiki's working tree to match an earlier commit and record
    the revert as a new commit, preserving full history. Returns the new
    commit sha, or ``None`` if git is unavailable or the revert failed."""
    if not _GIT_AVAILABLE:
        _warn_git_missing()
        return None

    path = wiki_dir(class_id)
    if not (path / ".git").exists():
        logger.warning("wiki_revert_failed", class_id=class_id, detail="no repo")
        return None

    checkout = _run_git(["checkout", commit_sha, "--", "."], cwd=path)
    if checkout.returncode != 0:
        logger.warning(
            "wiki_revert_failed",
            class_id=class_id,
            commit_sha=commit_sha,
            stderr=checkout.stderr.strip(),
        )
        return None

    return commit_wiki_change(class_id, f"Revert to {commit_sha[:8]}")
