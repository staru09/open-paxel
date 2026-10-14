from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from open_paxel.models.pipeline_models import GitCommit


def find_git_root(path: Path) -> Path:
    current = path
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return path


def read_git_log(project_path: str | Path, *, limit: int = 500) -> list[GitCommit]:
    path = find_git_root(Path(project_path))
    if not (path / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", f"-{limit}", "--format=%H|%aI|%s"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    commits: list[GitCommit] = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        hash_val, when, message = parts
        try:
            committed_at = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            continue
        commits.append(
            GitCommit(
                hash=hash_val,
                message=message,
                committed_at=committed_at,
                project_path=str(path.resolve()),
            )
        )
    return commits


def link_commits_to_session(
    commits: list[GitCommit],
    *,
    started_at: datetime | None,
    ended_at: datetime | None,
    slack_minutes: int = 30,
) -> list[str]:
    if not commits or not started_at:
        return []
    end = ended_at or started_at
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    slack = timedelta(minutes=slack_minutes)
    window_start = start - slack
    window_end = end + slack
    matched: list[str] = []
    for commit in commits:
        ts = commit.committed_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if window_start <= ts <= window_end:
            matched.append(commit.hash)
    return matched


def code_quality_label(project_path: str | Path) -> str:
    path = Path(project_path)
    if not path.exists():
        return "empty_repo"
    if not (path / ".git").exists():
        return "empty_repo"
    test_globs = list(path.glob("**/test_*.py")) + list(path.glob("**/*_test.py"))
    has_linter = any(
        (path / name).exists()
        for name in ("ruff.toml", ".ruff.toml", "pyproject.toml", "eslint.config.js")
    )
    if test_globs and has_linter:
        return "tested"
    if test_globs or has_linter:
        return "active"
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return "active"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "empty_repo"
