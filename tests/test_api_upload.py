from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from open_paxel.api.app import create_app
from open_paxel.config import Settings
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


@pytest.fixture
def client(tmp_path):
    settings = Settings(home=tmp_path / "home", ephemeral_jobs=True)
    settings.home.mkdir(parents=True)
    app = create_app(settings)

    original_init = AnalysisPipeline.__init__

    def patched_init(self, s, repository, parser=None, scorer=None):
        original_init(self, s, repository, parser=parser, scorer=MockScorer())

    with patch.object(AnalysisPipeline, "__init__", patched_init):
        with TestClient(app) as test_client:
            yield test_client


def test_upload_jsonl(client):
    fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
    files = [("files", ("sample.jsonl", fixture.read_bytes(), "application/jsonl"))]
    resp = client.post("/api/upload?sync=true", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["upload_id"]
    assert data["results"][0]["status"] == "ok"
    assert data["results"][0]["session_id"] == "test-session-001"


def test_upload_rejects_unsupported_format(client):
    files = [("files", ("notes.pdf", b"hello", "application/pdf"))]
    resp = client.post("/api/upload?sync=true", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 0
    assert data["failed"] == 1
    assert "unsupported" in data["results"][0]["error"].lower()


def test_upload_markdown(client):
    fixture = Path(__file__).parent / "fixtures" / "sample_session.md"
    files = [("files", ("sample_session.md", fixture.read_bytes(), "text/markdown"))]
    resp = client.post("/api/upload?sync=true", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["results"][0]["session_id"] == "md-session-001"


def test_upload_txt(client):
    fixture = Path(__file__).parent / "fixtures" / "sample_session.txt"
    files = [("files", ("sample_session.txt", fixture.read_bytes(), "text/plain"))]
    resp = client.post("/api/upload?sync=true", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == 1
    assert data["results"][0]["session_id"].startswith("import-")


def test_upload_empty_file_list(client):
    resp = client.post("/api/upload?sync=true", files=[])
    assert resp.status_code == 422


def test_upload_async_returns_job(client):
    fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
    files = [("files", ("sample.jsonl", fixture.read_bytes(), "application/jsonl"))]
    resp = client.post("/api/upload", files=files)
    assert resp.status_code == 202
    data = resp.json()
    assert data["job_id"]
    assert data["status"] == "queued"

    job_resp = client.get(f"/api/jobs/{data['job_id']}")
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["id"] == data["job_id"]
    assert job["logs"]
