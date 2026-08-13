from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LEGACY_ENV_ALIASES = {
    "BRAIN_DUMP_MODEL": "OPEN_PAXEL_MODEL",
    "BRAIN_DUMP_LLM_PROVIDER": "OPEN_PAXEL_LLM_PROVIDER",
    "BRAIN_DUMP_CONCURRENCY": "OPEN_PAXEL_CONCURRENCY",
    "BRAIN_DUMP_REDACTION_LEVEL": "OPEN_PAXEL_REDACTION_LEVEL",
    "BRAIN_DUMP_DRY_RUN": "OPEN_PAXEL_DRY_RUN",
    "BRAIN_DUMP_EPHEMERAL_JOBS": "OPEN_PAXEL_EPHEMERAL_JOBS",
    "BRAIN_DUMP_WORK_STREAM_GAP_HOURS": "OPEN_PAXEL_WORK_STREAM_GAP_HOURS",
    "BRAIN_DUMP_LEGACY_SCORER": "OPEN_PAXEL_LEGACY_SCORER",
}


def _apply_legacy_env_aliases() -> None:
    for legacy, current in _LEGACY_ENV_ALIASES.items():
        if legacy in os.environ and current not in os.environ:
            os.environ[current] = os.environ[legacy]


def default_home() -> Path:
    for key in ("OPEN_PAXEL_HOME", "BRAIN_DUMP_HOME"):
        if val := os.environ.get(key):
            return Path(val)
    open_paxel = Path.home() / ".open-paxel"
    legacy = Path.home() / ".brain-dump"
    if open_paxel.exists():
        return open_paxel
    if legacy.exists():
        return legacy
    return open_paxel


@lru_cache
def project_root() -> Path:
    """Repo root (directory containing pyproject.toml)."""
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parent


def env_file_paths() -> list[Path]:
    """`.env` files to load (first → last; later files do not override existing vars)."""
    home = default_home()
    return [
        project_root() / ".env",
        home / ".env",
    ]


def load_env_files(*, override: bool = False) -> list[Path]:
    """Load dotenv files into os.environ. Returns paths that were loaded."""
    loaded: list[Path] = []
    for path in env_file_paths():
        if path.is_file():
            load_dotenv(path, override=override)
            loaded.append(path)
    _apply_legacy_env_aliases()
    return loaded


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEN_PAXEL_",
        extra="ignore",
    )

    home: Path = Field(default_factory=default_home)
    host: str = "127.0.0.1"
    llm_provider: str = "openai"
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPEN_PAXEL_OPENAI_API_KEY", "BRAIN_DUMP_OPENAI_API_KEY"),
    )
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPEN_PAXEL_OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias=AliasChoices("OPEN_PAXEL_OLLAMA_BASE_URL", "OLLAMA_HOST"),
    )
    # Empty means "pick the provider's default" — see effective_model(). Keeping
    # this unset (rather than hardcoding an OpenAI model) lets OPEN_PAXEL_MODEL be
    # the single source of truth, so e.g. the bundled-Ollama container pulls and
    # the app requests the same model even when the user leaves it unset.
    model: str = ""
    concurrency: int = 3
    # Cap on response tokens per LLM call. Reasoning models (e.g. qwen3) spend a
    # large share on hidden reasoning, so the default must leave room for both the
    # reasoning trace AND the JSON answer, or content comes back empty.
    max_output_tokens: int = 8000
    # When a transcript's estimated tokens exceed this, condense it via a chunked
    # running-summary before scoring instead of sending the raw (overflowing) text.
    condense_over_est_tokens: int = 40_000
    # Chunk size in CHARACTERS (not estimated tokens — estimate_tokens under-counts
    # dense JSONL ~6x, so sizing by chars is the safe, deterministic choice).
    condense_chunk_chars: int = 120_000
    # Cap on condenser chunks. Beyond this, representative chunks are sampled
    # (first, last, evenly spaced) so a multi-million-token session stays bounded.
    condense_max_chunks: int = 12
    redaction_level: str = "standard"
    dry_run: bool = False
    ephemeral_jobs: bool = False
    work_stream_gap_hours: int = 48
    legacy_scorer: bool = False

    @property
    def db_path(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home / "profile.db"

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    def resolve_api_key(self) -> str | None:
        provider = self.llm_provider.lower()
        if provider == "openrouter":
            return self.openrouter_api_key
        if provider == "ollama":
            return None
        return self.openai_api_key

    def llm_configured(self) -> bool:
        """True when an LLM backend is available for scoring/narrative calls."""
        if self.dry_run:
            return False
        provider = self.llm_provider.lower()
        if provider == "ollama":
            return True
        if provider == "openrouter":
            return bool(self.openrouter_api_key)
        return bool(self.openai_api_key)

    def effective_model(self) -> str:
        if self.model:
            return self.model
        provider = self.llm_provider.lower()
        if provider == "ollama":
            return "llama3.2"
        if provider == "openrouter":
            return "openai/gpt-4o-mini"
        return "gpt-4.1-mini"

    @classmethod
    def load(cls) -> Settings:
        # 1) .env (project, then ~/.open-paxel/) — does not override existing env vars
        load_env_files(override=False)

        # 2) ~/.open-paxel/config.toml as defaults
        home = default_home()
        config_file = home / "config.toml"
        toml_data: dict = {}
        if config_file.exists():
            toml_data.update(_parse_simple_toml(config_file.read_text(encoding="utf-8")))

        # 3) pydantic-settings reads os.environ (wins over toml kwargs)
        return cls(**toml_data)


def _parse_simple_toml(text: str) -> dict:
    """Minimal TOML parser for flat key = value config."""
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.isdigit():
            result[key] = int(value)
        elif value.lower() in ("true", "false"):
            result[key] = value.lower() == "true"
        else:
            result[key] = value
    return result


def write_default_config(home: Path, api_key: str) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.toml"
    if path.exists():
        return path
    path.write_text(
        f'''# Open-Paxel configuration
llm_provider = "openai"
openai_api_key = "{api_key}"
model = "gpt-4.1-mini"
concurrency = 3
redaction_level = "standard"

# Max response tokens per LLM call. Reasoning models (e.g. qwen3) spend a large
# share on hidden reasoning, so leave room for the reasoning trace AND the JSON
# answer, or content can come back empty.
max_output_tokens = 8000

# Long transcripts are condensed into a running summary before scoring so they
# fit local-model context windows. Size chunks to ~half your model context (in
# characters) and cap chunk count to bound latency on huge sessions.
condense_over_est_tokens = 40000
condense_chunk_chars = 120000
condense_max_chunks = 12
''',
        encoding="utf-8",
    )
    return path
