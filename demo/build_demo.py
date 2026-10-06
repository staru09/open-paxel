"""Build the static demo site's data from a folder of Claude Code transcripts.

Runs the real pipeline (redaction included) into a throwaway home, then saves the
API responses the dashboard reads as JSON files:

    uv run python demo/build_demo.py <sessions_dir> demo/data   # writes demo/data/api/*.json

Only the fields the dashboard displays are exported (no prompts, traces, decisions,
paths to transcripts or pipeline artifacts). Run it locally and commit only the JSON,
so raw transcripts never reach the repo.
Uses OPENAI_API_KEY (or another configured provider) from the environment; without
a key the profile is heuristic-only.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from open_paxel.api.app import create_app
from open_paxel.config import Settings
from open_paxel.db.repository import SQLiteRepository
from open_paxel.pipeline.analysis import AnalysisPipeline
from open_paxel.pipeline.context import PipelineContext
from open_paxel.pipeline.orchestrator import PaxelPipeline
# Fields the demo pages render; everything else stays out of the public site.
PROFILE_FIELDS = ("archetype", "session_count", "upload_count", "dimensions", "insight_cards", "narrative")
SESSION_FIELDS = ("session_id", "title", "project_path", "archetype", "dimensions")


def pick(obj: dict, fields: tuple[str, ...]) -> dict:
    return {k: obj[k] for k in fields if k in obj}


async def analyze(settings: Settings, repo: SQLiteRepository, sessions: Path) -> None:
    pipeline = AnalysisPipeline(settings, repo)
    reports = [await pipeline.analyze_file(p) for p in sorted(sessions.glob("*.jsonl"))]
    projects = sorted({r.project_path for r in reports if r.project_path})
    upload = repo.create_upload([r.session_id for r in reports], projects)
    ctx = PipelineContext(reports=reports, project_path=projects[0], upload_id=upload.id)
    await PaxelPipeline(settings, repo).run_batch(ctx)


def main(sessions: Path, out_dir: Path) -> None:
    api = out_dir / "api"
    (api / "sessions").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as home:
        settings = Settings(home=Path(home))
        asyncio.run(analyze(settings, SQLiteRepository(settings.db_path), sessions))
        client = TestClient(create_app(settings))

        def get(route: str) -> dict:
            resp = client.get(f"/api/{route}")
            resp.raise_for_status()
            return resp.json()

        def write(name: str, data: dict) -> None:
            (api / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

        write("profile", pick(get("profile"), PROFILE_FIELDS))
        items = [pick(i, SESSION_FIELDS) for i in get("sessions?limit=100")["items"]]
        write("sessions", {"items": items})
        for item in items:
            sid = item["session_id"]
            write(f"sessions/{sid}", pick(get(f"sessions/{sid}"), SESSION_FIELDS))
    print(f"Wrote demo data to {api}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: build_demo.py <sessions_dir> <out_dir>")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
