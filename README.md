<p align="center">
  <img src="./assets/open.png" alt="Open-Paxel logo" width="180" />
</p>

# Open-Paxel

Local-first, open [Paxel](https://paxel.ycombinator.com/)-style analyzer for **Claude Code** sessions. Builds a historical builder profile across five dimensions (steering, execution, engineering, product instinct, and planning) with narrative sections, decision patterns, insight cards, and a neobrutalism dashboard.

**Privacy:** transcripts stay on your machine. Only redacted excerpts go to **your OpenAI API key**. Scores are stored locally in SQLite (`~/.open-paxel/profile.db`).

## Preview

<p align="center">
  <img src="./assets/main.png" alt="Open-Paxel profile: archetype, narrative, and what you built" width="720" />
</p>

<p align="center">
  <img src="./assets/hero.png" alt="Open-Paxel builder map and dimension scores" width="720" />
</p>

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python env and CLI tooling
- [Node.js](https://nodejs.org/) only if you run the frontend dev server
- An [OpenAI API key](https://platform.openai.com/api-keys)
- Claude Code sessions under `~/.claude/projects/` (for CLI discovery)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex
```

## Install

### pip (standard Python)

From PyPI (when published):

```bash
pip install open-paxel
```

From a clone of this repo:

```bash
git clone https://github.com/staru09/open-paxel.git
cd open-paxel

# Build the dashboard UI once (required for `open-paxel serve`)
cd frontend && npm install && npm run build && cd ..

pip install .
# editable / developer install:
pip install -e ".[dev]"
```

After install, the `open-paxel` command is on your PATH.

### uv (recommended for development)

From the repo root:

```bash
uv sync --all-groups          # creates .venv + installs deps
cp .env.example .env          # then add OPENAI_API_KEY=sk-...
```

**Optional:** install the CLI globally so you can run `open-paxel` from any project folder:

```bash
cd path/to/open-paxel
uv tool install --editable .
```

After that, `open-paxel discover` works from your project directory without `uv run`.

Or use the installer scripts (they only run `uv sync --all-groups`):

```bash
./install.sh      # Git Bash / macOS / Linux
./install.ps1     # Windows PowerShell
```

## Run with Docker

Prefer not to install `uv`, Python, and Node? Run the whole thing — frontend build
included — with one command. You only need Docker.

```bash
cp .env.example .env     # then edit: set your provider + key (or choose Ollama)
docker compose up        # → http://localhost:3847
```

That's it. The image builds the dashboard, serves it, and reads your Claude sessions
from `~/.claude` (mounted **read-only**), so `discover` and drag-and-drop upload both
work. Analysis results persist in a named volume across restarts.

### Fully local, no API key (bundled Ollama)

```bash
# In .env:  OPEN_PAXEL_LLM_PROVIDER=ollama   (OPEN_PAXEL_MODEL picks the model, default llama3.2)
docker compose --profile ollama up
```

This also starts a bundled Ollama container and, on first run, pulls the model named by
`OPEN_PAXEL_MODEL` into a persistent volume — no API key needed. `OPEN_PAXEL_MODEL` is the
single source of truth: it selects both the model the app uses and the one pulled. To use
an Ollama already installed on your host instead, set
`OPEN_PAXEL_DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` in `.env` and skip the profile.

### Lifecycle

```bash
docker compose up -d        # run in background
docker compose logs -f      # follow logs
docker compose down         # stop (data volume preserved)
docker compose build        # rebuild after code changes
```

Switching provider (OpenAI ↔ OpenRouter ↔ Ollama) is just a `.env` edit — no rebuild. Keep
every line in `.env` as strict `KEY=VALUE` or a `# comment`; `docker compose` rejects other
lines in an env file. The local dev workflow below (`uv run open-paxel dev`, `npm run dev`)
is unchanged and still binds `127.0.0.1`.

## Configure API key

**Credential priority** (highest first):

1. Shell environment (`OPENAI_API_KEY`, `OPEN_PAXEL_*`)
2. [`.env`](.env) in the project root
3. `~/.open-paxel/.env` (or legacy `~/.brain-dump/.env`)
4. `~/.open-paxel/config.toml` (or legacy `~/.brain-dump/config.toml`)

```env
# .env
OPENAI_API_KEY=sk-...
OPEN_PAXEL_MODEL=gpt-4.1-mini
OPEN_PAXEL_CONCURRENCY=3
```

Or create config interactively:

```bash
uv run open-paxel init-config
```

```toml
# ~/.open-paxel/config.toml
llm_provider = "openai"
openai_api_key = "sk-..."
model = "gpt-4.1-mini"
concurrency = 3
```

Legacy `BRAIN_DUMP_*` env vars and `~/.brain-dump/` data paths are still supported if you already have an existing install.

### Use Ollama (local LLM, no OpenAI key)

1. Install and start [Ollama](https://ollama.com/)
2. Pull a model:

```bash
ollama pull llama3.2
```

3. Configure Open-Paxel:

```env
# .env
OPEN_PAXEL_LLM_PROVIDER=ollama
OPEN_PAXEL_MODEL=llama3.2
OPEN_PAXEL_OLLAMA_BASE_URL=http://localhost:11434/v1
```

Or in `~/.open-paxel/config.toml`:

```toml
llm_provider = "ollama"
model = "llama3.2"
ollama_base_url = "http://localhost:11434/v1"
```

No API key is required. Open-Paxel uses Ollama's OpenAI-compatible API for session narratives, decision classification, episode scoring, and profile generation.

For best results, use a model that follows JSON instructions well (e.g. `llama3.2`, `qwen2.5`, `mistral`).

### Use OpenRouter (multi-model API)

[OpenRouter](https://openrouter.ai/) exposes many models through one OpenAI-compatible API.

1. Create an API key at [openrouter.ai/keys](https://openrouter.ai/keys)
2. Configure Open-Paxel:

```env
# .env
OPEN_PAXEL_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPEN_PAXEL_MODEL=openai/gpt-4o-mini
```

Or in `~/.open-paxel/config.toml`:

```toml
llm_provider = "openrouter"
openrouter_api_key = "sk-or-v1-..."
model = "anthropic/claude-3.5-sonnet"
openrouter_base_url = "https://openrouter.ai/api/v1"
```

Model IDs use OpenRouter's `provider/model` format (e.g. `openai/gpt-4o-mini`, `anthropic/claude-3.5-sonnet`, `google/gemini-flash-1.5`). Open-Paxel tries structured outputs first and falls back to JSON prompting when a model does not support them.

## How to use

### Recommended: CLI from your project folder

Open-Paxel discovers Claude Code sessions for **the current working directory only**. Run these commands from the root of the project you used with Claude Code (not from the Open-Paxel repo itself, unless that is your Claude project).

```powershell
# Example: your Claude project (folder name may differ from Claude's stored path)
cd project-directory/

open-paxel discover          # shows matched project + session count
open-paxel upload -y         # analyze all new sessions + run full pipeline
open-paxel profile           # print profile in the terminal
open-paxel profile --open    # start server and open dashboard
```

Typical flow:

1. **`discover`** finds the Claude Code project whose path matches your CWD. Handles aliases like `gpu_visuals` → `gpu\visuals`.
2. **`upload -y`** parses each `.jsonl` transcript, scores the session with the LLM, then runs the Paxel batch pipeline (git history, commit linking, decisions, episodes, profile assembly).
3. **`profile`** or **`serve`** shows the aggregated builder profile.

If `discover` finds nothing, `cd` into the directory Claude Code actually used (check `~/.claude/projects/` encoded folder names) or upload files via the dashboard (see below).

### Dashboard (web UI)

**Production-style:** serves the built frontend from the Python app:

```bash
uv run open-paxel serve
# → http://127.0.0.1:3847
```

**Development:** hot-reload frontend + backend:

```bash
uv run open-paxel dev --open
# Backend: http://127.0.0.1:3847   Frontend: http://127.0.0.1:5173
```

Pages:

| Page | What it shows |
|------|----------------|
| **Profile** | Archetype, dimension scores, narrative sections, decision patterns, insight cards |
| **Sessions** | Per-session scores, titles, and detail view |
| **Uploads** | Drag-and-drop session files; background job progress |

The UI reads the same SQLite database as the CLI. Run `upload` from the CLI, then refresh the dashboard, or upload directly in the UI.

### Upload via dashboard

Supported formats: `.jsonl`, `.md`, `.markdown`, `.txt`

| Format | Git integration | Notes |
|--------|-----------------|-------|
| **`.jsonl`** (Claude Code export) | Full if `cwd` in transcript points to a repo with `.git` | Best option for complete analysis |
| **`.md` / `.txt`** | Partial only if you add YAML frontmatter | Transcript analysis always runs; git needs metadata |

For markdown/text exports, optional frontmatter enables git log and code-quality labels:

```markdown
---
title: My session
project: C:\path\to\your\repo
---

## User
...
```

Plain text without frontmatter still gets transcript analysis (narrative, decisions, heuristics) but **no git commit linking**. For full git correlation, use CLI `upload` from the project folder or upload the original `.jsonl`.

Re-analyze an already-imported session with the **Force re-analyze** checkbox on the Uploads page, or `open-paxel upload --force -y` from the CLI.

## Commands

With global install, drop the `uv run` prefix. From the repo without global install, use `uv run open-paxel ...`.

| Command | Description |
|---------|-------------|
| `open-paxel discover` | Show Claude Code project + sessions for **current directory** |
| `open-paxel upload -y` | Batch analyze new sessions + Paxel pipeline |
| `open-paxel upload --force -y` | Re-analyze all sessions |
| `open-paxel analyze <file.jsonl>` | Analyze one transcript |
| `open-paxel analyze --latest` | Analyze most recent session for CWD project |
| `open-paxel profile` | Print profile (text) |
| `open-paxel profile --format json` | Print profile as JSON |
| `open-paxel profile --open` | Serve dashboard and open browser |
| `open-paxel list` | List analyzed sessions |
| `open-paxel serve` | Run FastAPI + dashboard |
| `open-paxel dev --open` | Dev servers (backend + Vite) |
| `open-paxel reset -y` | Wipe local data (keeps config) |
| `open-paxel init-config` | Write `~/.open-paxel/config.toml` |

## What gets analyzed

Per session:

- Transcript parsing (tools, redirects, test/lint mentions, heuristics)
- LLM session narrative and dimension scoring
- Steering traces and decision extraction (matched against `assets/decision_catalog.json`)

After upload (batch pipeline):

- Git log read and commits linked to session time window (JSONL / CLI upload)
- Work streams grouped across sessions
- Episode scoring and builder profile assembly

## Data location

| Path | Contents |
|------|----------|
| `~/.open-paxel/profile.db` | Sessions, scores, profile, upload history |
| `~/.open-paxel/config.toml` | API key and settings (if created) |
| `~/.open-paxel/incoming/` | Temp files from UI uploads |
| `~/.claude/projects/` | Claude Code session `.jsonl` files (read-only) |

If you used the old **Brain Dump** install, data may still live under `~/.brain-dump/`. Open-Paxel picks that up automatically until you migrate.

## Claude Code plugin

Install the CLI globally so SessionEnd hooks find `open-paxel`:

```bash
uv tool install --editable .
claude --plugin-dir ./plugin
```

Skills: `/session-profile:analyze`, `/session-profile:profile`, `/session-profile:upload`

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check open_paxel

# Backend + frontend together
uv run open-paxel dev --open

# Or separately
uv run open-paxel serve
cd frontend && npm install && npm run dev

# Build frontend into open_paxel/static/ for production serve
cd frontend && npm run build
```

## License

MIT
