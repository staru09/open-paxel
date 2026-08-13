from pathlib import Path

from open_paxel.config import Settings, load_env_files, project_root


def test_load_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('OPENAI_API_KEY="sk-test-from-env-file"\n', encoding="utf-8")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("open_paxel.config.env_file_paths", lambda: [env_file])

    load_env_files()
    settings = Settings.load()

    assert settings.resolve_api_key() == "sk-test-from-env-file"


def test_env_overrides_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-shell")
    monkeypatch.setenv("BRAIN_DUMP_HOME", str(tmp_path / "home"))

    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text('openai_api_key = "sk-from-toml"\n', encoding="utf-8")

    monkeypatch.setattr("open_paxel.config.load_env_files", lambda **_: [])

    settings = Settings.load()
    assert settings.resolve_api_key() == "sk-from-shell"


def test_project_root_has_pyproject():
    assert (project_root() / "pyproject.toml").exists()


def test_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("OPEN_PAXEL_HOST", raising=False)
    monkeypatch.setattr("open_paxel.config.load_env_files", lambda **_: [])

    settings = Settings.load()

    assert settings.host == "127.0.0.1"


def test_host_overridable_via_env(monkeypatch):
    monkeypatch.setenv("OPEN_PAXEL_HOST", "0.0.0.0")
    monkeypatch.setattr("open_paxel.config.load_env_files", lambda **_: [])

    settings = Settings.load()

    assert settings.host == "0.0.0.0"
