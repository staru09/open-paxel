import pytest

from open_paxel.config import Settings
from open_paxel.db.repository import SQLiteRepository
from open_paxel.models.domain import DimensionScore, SessionScore
from open_paxel.pipeline import AnalysisPipeline


class MockScorer:
    async def score_session(self, facts, metrics, excerpts):
        return SessionScore(
            dimensions={
                d: DimensionScore(score=70.0, narrative="mock", evidence=["e1"])
                for d in ("steering", "execution", "engineering", "product_instinct", "planning")
            },
            archetype="Architect",
            signature_moves=["Plans before coding"],
            growth_edge=["Add more tests"],
        )


@pytest.mark.asyncio
async def test_pipeline_dry_run(tmp_path):
    import shutil
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
    target = tmp_path / "sample.jsonl"
    shutil.copy(fixture, target)

    settings = Settings(home=tmp_path / "home", dry_run=True)
    settings.home.mkdir(parents=True)
    repo = SQLiteRepository(settings.db_path)
    pipeline = AnalysisPipeline(settings, repo, scorer=MockScorer())

    report = await pipeline.analyze_file(target)
    assert report.archetype == "Architect"
    assert report.dimensions["steering"].score > 0
    assert not repo.report_exists(report.session_id)
