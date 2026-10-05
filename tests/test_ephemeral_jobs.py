from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from open_paxel.api.app import create_app
from open_paxel.config import Settings
from open_paxel.pipeline import AnalysisPipeline
from tests.test_api_upload import MockScorer


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


def test_ephemeral_jobs_cleared_on_startup(tmp_path):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    incoming = home / "incoming"
    incoming.mkdir()
    stale_file = incoming / "stale.txt"
    stale_file.write_text("leftover", encoding="utf-8")

    settings = Settings(home=home, ephemeral_jobs=True)
    app = create_app(settings)
    with TestClient(app):
        repo = app.state.repository
        job = repo.create_job(total_count=1)
        assert repo.get_job(job.id) is not None

    # New server instance should wipe jobs and incoming files
    app2 = create_app(settings)
    with TestClient(app2) as client2:
        assert client2.get("/api/jobs").json() == []
        assert not stale_file.exists()
        health = client2.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["instance_id"]


def test_ephemeral_jobs_persist_when_disabled(tmp_path):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    settings = Settings(home=home, ephemeral_jobs=False)

    app = create_app(settings)
    with TestClient(app):
        repo = app.state.repository
        job = repo.create_job(total_count=1)
        job_id = job.id

    app2 = create_app(settings)
    with TestClient(app2) as client2:
        assert client2.get(f"/api/jobs/{job_id}").status_code == 200
