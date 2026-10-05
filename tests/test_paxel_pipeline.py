import json
from pathlib import Path

from open_paxel.decisions.catalog import catalog_by_key, load_decision_catalog
from open_paxel.discover.scanner import (
    RepoInfo,
    _claude_encoded_key,
    discover_repo_for_cwd,
    filter_repos_by_cwd,
)


def test_decision_catalog_loads():
    patterns = load_decision_catalog()
    assert len(patterns) >= 40
    assert "model-the-data-owner" in catalog_by_key()


def test_filter_repos_by_cwd_exact():
    repos = [
        RepoInfo(
            name="open_paxel",
            path=r"Z:\June 26\open_paxel",
            encoded_dir="x",
            session_count=1,
            session_paths=[],
        ),
        RepoInfo(
            name="other",
            path=r"Z:\Other\project",
            encoded_dir="y",
            session_count=1,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"Z:\June 26\open_paxel"))
    assert len(matched) == 1
    assert matched[0].name == "open_paxel"


def test_filter_repos_ignores_user_home_false_positive():
    repos = [
        RepoInfo(
            name="91745",
            path=r"C:\Users\91745",
            encoded_dir="home",
            session_count=1,
            session_paths=[],
        ),
        RepoInfo(
            name="io",
            path=r"C:\Users\91745\OneDrive\Desktop\staru09\github\io",
            encoded_dir="io",
            session_count=1,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"C:\Users\91745\OneDrive\Desktop\staru09\github\io"))
    assert len(matched) == 1
    assert matched[0].name == "io"


def test_discover_repo_prefers_longest_match():
    repos = [
        RepoInfo(
            name="91745",
            path=r"C:\Users\91745",
            encoded_dir="home",
            session_count=1,
            session_paths=[],
        ),
        RepoInfo(
            name="visuals",
            path=r"C:\Users\91745\OneDrive\Desktop\gpu\visuals",
            encoded_dir="gpu",
            session_count=2,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"C:\Users\91745\OneDrive\Desktop\gpu\visuals"))
    assert len(matched) == 1
    assert matched[0].name == "visuals"


def test_filter_repos_matches_gpu_visuals_alias():
    repos = [
        RepoInfo(
            name="visuals",
            path=r"C:\Users\91745\OneDrive\Desktop\gpu\visuals",
            encoded_dir="C--Users-91745-OneDrive-Desktop-gpu-visuals",
            session_count=2,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"C:\Users\91745\OneDrive\Desktop\gpu_visuals"))
    assert len(matched) == 1
    assert matched[0].name == "visuals"


def test_malformed_io_path_does_not_match_unrelated_cwd():
    repos = [
        RepoInfo(
            name="io",
            path="c//Users/91745/OneDrive/Desktop/staru09/github/io",
            encoded_dir="bad",
            session_count=1,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"Z:\June 26\open_paxel"))
    assert matched == []


def test_filter_repos_matches_audiobook_generator_encoded_key():
    repos = [
        RepoInfo(
            name="generator",
            path=r"Z:\June\26\audiobook\generator",
            encoded_dir="Z--June-26-audiobook-generator",
            session_count=1,
            session_paths=[],
        ),
    ]
    matched = filter_repos_by_cwd(repos, Path(r"Z:\June 26\audiobook_generator"))
    assert len(matched) == 1
    assert matched[0].encoded_dir == "Z--June-26-audiobook-generator"


def test_discover_repo_reads_real_path_from_transcript_cwd(tmp_path):
    # "my_app.v2" encodes to "...-my-app-v2"; decoding alone would give my/app/v2.
    project = tmp_path / "work" / "my_app.v2"
    project.mkdir(parents=True)
    projects_root = tmp_path / "projects"
    folder = projects_root / _claude_encoded_key(project.resolve())
    folder.mkdir(parents=True)
    (folder / "s1.jsonl").write_text(
        json.dumps({"type": "summary"}) + "\n" + json.dumps({"cwd": str(project.resolve())}) + "\n",
        encoding="utf-8",
    )

    repo = discover_repo_for_cwd(project, projects_root=projects_root)

    assert repo is not None
    assert repo.path == str(project.resolve())
    assert repo.name == "my_app.v2"
    assert repo.session_count == 1


def test_claude_encoded_key_posix():
    # POSIX roots encode with a single leading dash (no drive letter).
    key = _claude_encoded_key(Path("/Users/surya/ai/projects/mcp-postgres-oidc"))
    assert key == "-users-surya-ai-projects-mcp-postgres-oidc"


def test_filter_repos_ignores_posix_user_home_false_positive():
    # Regression: on macOS/Linux the home project (/Users/<name>) must not
    # swallow a sub-project CWD. The real project is recovered via the
    # encoded-key fingerprint even though hyphen-decoding mangles its path
    # (mcp-postgres-oidc -> mcp/postgres/oidc).
    repos = [
        RepoInfo(
            name="surya",
            path="/Users/surya",
            encoded_dir="-Users-surya",
            session_count=20,
            session_paths=[],
        ),
        RepoInfo(
            name="oidc",
            path="/Users/surya/ai/projects/mcp/postgres/oidc",
            encoded_dir="-Users-surya-ai-projects-mcp-postgres-oidc",
            session_count=2,
            session_paths=[],
        ),
    ]
    cwd = Path("/Users/surya/ai/projects/mcp-postgres-oidc")
    matched = filter_repos_by_cwd(repos, cwd)
    assert len(matched) == 1
    assert matched[0].encoded_dir == "-Users-surya-ai-projects-mcp-postgres-oidc"
    assert matched[0].session_count == 2


def test_work_streams_single_project():
    from datetime import datetime, timedelta

    from open_paxel.models.domain import SessionReport
    from open_paxel.pipeline.steps.work_streams import build_work_streams

    base = datetime(2026, 6, 1, 10, 0)
    reports = [
        SessionReport(
            session_id="a",
            transcript_path="a.jsonl",
            project_path="/p",
            started_at=base,
            ended_at=base + timedelta(hours=1),
        ),
        SessionReport(
            session_id="b",
            transcript_path="b.jsonl",
            project_path="/p",
            started_at=base + timedelta(days=3),
            ended_at=base + timedelta(days=3, hours=2),
        ),
    ]
    streams = build_work_streams(reports, gap_hours=48)
    assert len(streams) == 2
