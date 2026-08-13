from __future__ import annotations

import os
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


def _fix_malformed_windows_path(path: str) -> str:
    """Repair paths like c//Users/... from legacy decode fallbacks."""
    normalized = path.replace("/", "\\")
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == "/":
        normalized = normalized[0].upper() + ":" + normalized[1:].lstrip("/\\")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] != "\\":
        normalized = normalized[:2] + "\\" + normalized[2:].lstrip("\\")
    return normalized


def _normalize_path(path: str) -> str:
    fixed = _fix_malformed_windows_path(path)
    candidate = Path(fixed)
    try:
        if candidate.is_absolute():
            return str(candidate.resolve()).lower().replace("/", "\\")
    except OSError:
        pass
    return str(candidate).lower().replace("/", "\\")


def _is_windows_path(path: Path | str) -> bool:
    path_str = str(path)
    if len(path_str) >= 2 and path_str[0].isalpha() and (path_str[1] == ":" or path_str[1] == "/" or path_str[1] == "\\"):
        return True
    return False


def _resolve_path(path: Path) -> Path:
    if os.name != 'nt' and _is_windows_path(path):
        return path
    return path.resolve()


def _claude_encoded_key(path: Path) -> str:
    """Fingerprint matching Claude's ~/.claude/projects folder names.

    Windows drives encode as ``c--users-name``; POSIX roots encode with a
    single leading dash, e.g. ``/Users/surya`` -> ``-Users-surya``.
    """
    resolved = _resolve_path(path)
    path_str = str(resolved)
    if _is_windows_path(path_str):
        drive = path_str[0].lower()
        rest = path_str[2:]
        if rest.startswith("/") or rest.startswith("\\"):
            rest = rest[1:]
        normalized_rest = rest.replace("\\", "/")
        parts = [p for p in normalized_rest.split("/") if p]
        segments = [part.replace(" ", "-").replace("_", "-").lower() for part in parts]
        return f"{drive}--" + "-".join(segments)

    parts = list(resolved.parts)
    if not parts:
        return ""
    segments = [part.replace(" ", "-").replace("_", "-").lower() for part in parts[1:]]
    if parts[0] == "/":  # POSIX root
        return "-" + "-".join(segments)
    drive = parts[0][0].lower()  # Windows drive letter
    return f"{drive}--" + "-".join(segments)


def _encoded_key_match(repo: RepoInfo, cwd: Path) -> bool:
    return repo.encoded_dir.lower() == _claude_encoded_key(cwd)


def _cwd_path_variants(cwd: Path) -> list[str]:
    """Include aliases such as gpu_visuals vs gpu\\visuals."""
    resolved = _resolve_path(cwd)
    variants = {_normalize_path(str(resolved))}
    
    path_str = str(resolved)
    if _is_windows_path(path_str):
        rest = path_str
        normalized = rest.replace("/", "\\")
        parts = [p for p in normalized.split("\\") if p]
    else:
        parts = list(resolved.parts)

    if parts:
        leaf = parts[-1]
        if "_" in leaf:
            if _is_windows_path(path_str):
                alt_parts = list(parts[:-1]) + leaf.split("_")
                if alt_parts[0].endswith(":"):
                    alt_str = alt_parts[0] + "\\" + "\\".join(alt_parts[1:])
                else:
                    alt_str = "\\".join(alt_parts)
                variants.add(_normalize_path(alt_str))
            else:
                alt = Path(*parts[:-1], *leaf.split("_"))
                variants.add(_normalize_path(str(alt)))
    return sorted(variants)


def _is_user_home_false_positive(repo_norm: str, cwd_norm: str) -> bool:
    if repo_norm == cwd_norm:
        return False
    parts = [p for p in repo_norm.split("\\") if p]
    # Windows user home: C:\Users\name -> (drive, "users", name)
    if len(parts) == 3 and parts[1] == "users":
        return True
    # POSIX user home: /Users/name or /home/name -> ("users"|"home", name)
    return len(parts) == 2 and parts[0] in ("users", "home")


def _paths_match(repo_path: str, cwd_variants: list[str]) -> bool:
    repo_norm = _normalize_path(repo_path)
    for cwd_norm in cwd_variants:
        if repo_norm == cwd_norm:
            return True
        if cwd_norm.startswith(repo_norm + "\\"):
            if _is_user_home_false_positive(repo_norm, cwd_norm):
                continue
            return True
        if repo_norm.startswith(cwd_norm + "\\"):
            return True
    return False


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
        decoded = decode_project_path(entry.name)
        name = Path(decoded).name or entry.name
        repos.append(
            RepoInfo(
                name=name,
                path=decoded,
                encoded_dir=entry.name,
                session_count=len(sessions),
                session_paths=sessions,
            )
        )
    return repos


def filter_repos_by_cwd(repos: list[RepoInfo], cwd: Path) -> list[RepoInfo]:
    cwd_variants = _cwd_path_variants(cwd)
    return [
        repo
        for repo in repos
        if _paths_match(repo.path, cwd_variants) or _encoded_key_match(repo, cwd)
    ]


def _correct_repo_path(repo: RepoInfo, cwd: Path) -> RepoInfo:
    """Use the real CWD when Claude's encoded folder name matches but decode is ambiguous."""
    cwd_str = str(cwd)
    if _normalize_path(repo.path) == _normalize_path(cwd_str):
        return repo
    name = cwd.name
    if "\\" in name:
        name = name.split("\\")[-1]
    return replace(repo, path=cwd_str, name=name or repo.name)


def discover_repo_for_cwd(cwd: Path | None = None) -> RepoInfo | None:
    """Return the single Claude Code repo matching the current working directory."""
    cwd = (cwd or Path.cwd()).resolve()
    matched = filter_repos_by_cwd(discover_repos(), cwd)
    if not matched:
        return None
    cwd_variants = set(_cwd_path_variants(cwd))
    encoded_key = _claude_encoded_key(cwd)
    for repo in matched:
        if repo.encoded_dir.lower() == encoded_key:
            return _correct_repo_path(repo, cwd)
    for repo in matched:
        if _normalize_path(repo.path) in cwd_variants:
            return repo
    return _correct_repo_path(
        max(matched, key=lambda r: len(_normalize_path(r.path))),
        cwd,
    )
