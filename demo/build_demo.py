"""Build the static demo site's data from the fictional sessions in demo/sessions/.

Runs the real pipeline into a throwaway home, then saves the API responses the
dashboard reads as JSON files:

    uv run python demo/build_demo.py site     # writes site/api/*.json

Without an API key the profile is heuristic-only; set OPENAI_API_KEY (or another
provider) to include LLM narratives.
"""

from __future__ import annotations

import asyncio
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

SESSIONS = Path(__file__).parent / "sessions"


async def analyze(settings: Settings, repo: SQLiteRepository) -> None:
    pipeline = AnalysisPipeline(settings, repo)
    reports = [await pipeline.analyze_file(p) for p in sorted(SESSIONS.glob("*.jsonl"))]
    projects = sorted({r.project_path for r in reports if r.project_path})
    upload = repo.create_upload([r.session_id for r in reports], projects)
    ctx = PipelineContext(reports=reports, project_path=projects[0], upload_id=upload.id)
    await PaxelPipeline(settings, repo).run_batch(ctx)


def main(out_dir: Path) -> None:
    api = out_dir / "api"
    (api / "sessions").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as home:
        settings = Settings(home=Path(home))
        asyncio.run(analyze(settings, SQLiteRepository(settings.db_path)))
        client = TestClient(create_app(settings))

        def save(route: str, name: str) -> dict:
            resp = client.get(f"/api/{route}")
            resp.raise_for_status()
            (api / f"{name}.json").write_text(resp.text, encoding="utf-8")
            return resp.json()

        save("profile", "profile")
        for item in save("sessions?limit=100", "sessions")["items"]:
            save(f"sessions/{item['session_id']}", f"sessions/{item['session_id']}")
    print(f"Wrote demo data to {api}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
