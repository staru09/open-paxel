from __future__ import annotations

import uvicorn
from typer.testing import CliRunner

from open_paxel.cli import app

runner = CliRunner()


def _captured_host(monkeypatch, *args, env=None):
    """Invoke `serve` with uvicorn.run mocked, return the host it was called with."""
    captured: dict = {}

    def fake_run(*_args, **kwargs):
        captured["host"] = kwargs.get("host")

    monkeypatch.setattr(uvicorn, "run", fake_run)
    # Keep the test hermetic: don't let Settings.load() import the repo's real .env
    # into os.environ (load_dotenv mutates it permanently and pollutes other tests).
    monkeypatch.setattr("open_paxel.config.load_env_files", lambda **_: [])
    monkeypatch.delenv("OPEN_PAXEL_HOST", raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)

    result = runner.invoke(app, ["serve", "--no-reload", *args])
    assert result.exit_code == 0, result.output
    return captured["host"]


def test_serve_defaults_to_loopback(monkeypatch):
    assert _captured_host(monkeypatch) == "127.0.0.1"


def test_serve_binds_host_from_env(monkeypatch):
    assert _captured_host(monkeypatch, env={"OPEN_PAXEL_HOST": "0.0.0.0"}) == "0.0.0.0"


def test_serve_explicit_host_flag_wins_over_env(monkeypatch):
    host = _captured_host(monkeypatch, "--host", "0.0.0.0", env={"OPEN_PAXEL_HOST": "127.0.0.1"})
    assert host == "0.0.0.0"
