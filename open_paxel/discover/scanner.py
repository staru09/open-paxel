from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from open_paxel.parser.claude_jsonl import decode_project_path


@dataclass
class RepoInfo:
    name: str
    path: str
    encoded_dir: str
    session_count: int
    session_paths: list[Path]


def find_claude_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def _claude_encoded_key(path: str | Path) -> str:
    """Claude names ~/.claude/projects folders by replacing every non-alphanumeric
    character of the project path with ``-`` (``Z:\\June 26\\a_b`` -> ``Z--June-26-a-b``).
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(path)).lower()


def _session_cwd(sessions: list[Path], encoded_dir: str) -> str | None:
    """The real project path: the first transcript ``cwd`` that encodes to ``encoded_dir``.

    Folder-name decoding is lossy (``-`` could be ``/``, `` ``, ``_`` or ``.``), so
    prefer the path Claude recorded. ``cwd`` can drift after ``cd``, hence the key check.
    """
    key = encoded_dir.lower()
    for path in sessions:
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        cwd = json.loads(line).get("cwd")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if cwd and _claude_encoded_key(cwd) == key:
                        return cwd
        except OSError:
            continue
    return None


def _normalize_path(path: str | Path) -> str:
    """Case- and separator-insensitive form; no resolve() so Windows paths compare on POSIX."""
    return str(path).replace("\\", "/").rstrip("/").lower()


def _is_user_home(repo_norm: str) -> bool:
    parts = [p for p in repo_norm.split("/") if p]
    # Windows C:\Users\name -> (drive, "users", name); POSIX /Users/name or /home/name
    if len(parts) == 3 and parts[1] == "users":
        return True
    return len(parts) == 2 and parts[0] in ("users", "home")


def _paths_match(repo_path: str, cwd: Path) -> bool:
    repo_norm = _normalize_path(repo_path)
    cwd_norm = _normalize_path(cwd)
    if repo_norm == cwd_norm or repo_norm.startswith(cwd_norm + "/"):
        return True
    # CWD inside the repo, except the user-home project swallowing every sub-project.
    return cwd_norm.startswith(repo_norm + "/") and not _is_user_home(repo_norm)


def discover_repos(projects_root: Path | None = None) -> list[RepoInfo]:
    root = projects_root or find_claude_projects_root()
    if not root.exists():
        return []

    repos: list[RepoInfo] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        sessions = [
            p for p in entry.glob("*.jsonl") if p.is_file() and not p.name.startswith(".")
        ]
        if not sessions:
            continue
        path = _session_cwd(sessions, entry.name) or decode_project_path(entry.name)
        repos.append(
            RepoInfo(
                name=Path(path.replace("\\", "/")).name or entry.name,
                path=path,
                encoded_dir=entry.name,
                session_count=len(sessions),
                session_paths=sessions,
            )
        )
    return repos


def filter_repos_by_cwd(repos: list[RepoInfo], cwd: Path) -> list[RepoInfo]:
    key = _claude_encoded_key(cwd)
    return [r for r in repos if r.encoded_dir.lower() == key or _paths_match(r.path, cwd)]


def discover_repo_for_cwd(
    cwd: Path | None = None, projects_root: Path | None = None
) -> RepoInfo | None:
    """Return the single Claude Code repo matching the current working directory."""
    cwd = (cwd or Path.cwd()).resolve()
    matched = filter_repos_by_cwd(discover_repos(projects_root), cwd)
    if not matched:
        return None
    key = _claude_encoded_key(cwd)
    for repo in matched:
        if repo.encoded_dir.lower() == key:
            # Exact project folder: trust the real CWD over a lossy decode.
            return replace(repo, path=str(cwd), name=cwd.name or repo.name)
    return max(matched, key=lambda r: len(_normalize_path(r.path)))
