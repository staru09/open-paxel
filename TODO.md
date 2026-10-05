# TODO

Findings from the codebase review (2026-10-05), ordered by priority.

## P0 — Privacy and data-loss bugs

- [x] **Redact transcripts before condensing.** `pipeline/analysis.py` passes raw
  `read_full_transcript()` output (full JSONL, tool outputs, file contents) into
  `condense_transcript()`. `chunk_summary_user_prompt()` embeds chunks unredacted;
  `redact_text` only runs on the dry-run path. Fix: `redact_text(full_text, max_len=…)`
  once in `analysis.py` before condensing.
- [x] **Broaden secret patterns** in `redact/transcript.py`. Currently not redacted:
  `sk-ant-api03-…` (Anthropic), `ghp_…`/`github_pat_…` (GitHub), `AKIA…` (AWS),
  JSON-style `"api_key": "…"`. Add a test with one sample per pattern.
- [x] **Wire up or delete `redaction_level`** (`config.py`) — declared, never read.
- [x] **Stop overwriting the enriched profile.** `save_report`, `update_report_title` and
  `create_upload` call `_refresh_profile_cache()`, which rebuilds a heuristic-only profile
  and overwrites the LLM narrative/episodes saved by `assemble_profile`. Renaming a session
  wipes paid-for LLM output. Fix: remove refresh from write paths; keep lazy build in
  `get_profile()` only.
- [x] **Profile only reflects the latest batch.** `assemble_profile` takes episodes and
  episode dimensions from the current `PipelineContext` only; a second upload replaces
  earlier episodes. Persist episodes and aggregate across all uploads.
- [x] **Keep a reference to background upload tasks** (`api/routes/uploads.py`).
  Bare `asyncio.create_task()` can be garbage-collected mid-run. Use a module-level set +
  `task.add_done_callback(set.discard)`.

## P1 — Discovery and tests

- [x] **Read `cwd` from JSONL instead of decoding folder names.** Every record carries the
  real `cwd`. `discover_repos()` can read the first `cwd` from one session per folder,
  removing most of `decode_project_path` (only handles `C:`/`Z:`), path-fix and
  correction logic in `discover/scanner.py`.
- [x] If the fingerprint stays: Claude's encoding is `re.sub(r"[^A-Za-z0-9]", "-", path)`;
  current `_claude_encoded_key` misses `.` (e.g. `my.app`, `~/.config`).
- [x] **Fix 6 failing discovery tests on Linux/macOS** (`tests/test_paxel_pipeline.py`).
  They use `Path(r"Z:\…")`, which resolves under CWD on POSIX. Use `PureWindowsPath`,
  `skipif`, or delete with the item above.
- [x] **Add CI**: GitHub Actions matrix (windows/macos/ubuntu) running `uv run pytest` and
  `uv run ruff check open_paxel tests`.
- [x] `uv run ruff check --fix open_paxel tests` (27 errors, 23 auto-fixable).
- [x] Replace `datetime.utcnow()` (10 call sites, 151 test warnings) with `datetime.now(UTC)`.

## P2 — Performance and robustness

- [x] Per-report profile rebuild is O(batch × total sessions) — resolved by the P0 cache fix.
- [x] `git/reader.py:code_quality_label` globs `**/test_*.py` through `node_modules`/`.venv`.
  Use `git ls-files`.
- [ ] "`pyproject.toml` exists" counts as having a linter in `code_quality_label` — weak signal.
- [x] Upload size cap in `api/routes/uploads.py` (files read fully into memory).
- [x] Remove empty step 5 in `pipeline/orchestrator.py` (or give it real work).

## P3 — Repo hygiene

- [x] Delete root `package-lock.json` (empty stub).
- [x] Untrack `frontend/tsconfig.tsbuildinfo`; add to `.gitignore`.
- [x] Drop unused `anthropic` optional extra from `pyproject.toml`.
- [ ] Dedupe dev deps (`[project.optional-dependencies].dev` vs `[dependency-groups].dev`).
  Kept for now: README's `pip install -e ".[dev]"` needs the extra, uv uses the group.
  Drop the extra once README switches to `pip install -e . --group dev` (pip >= 25.1).
- [x] Reformat `redact/excerpts.py` (blank line after every line).

## Also fixed during the refactor

- [x] `openai_api_key` in `config.toml` (written by `init-config`) was ignored: aliased fields
  need `populate_by_name`. Env vars now override `config.toml`, as the README says.
- [x] Circular import: importing `open_paxel.scorer` first failed. Removed unused package
  re-exports from `__init__.py` files.
- [x] One `SQLiteRepository` per CLI command (upload opened a new engine per session).
- [x] Replaced the hand-rolled TOML parser with stdlib `tomllib`; removed `dev.py`
  (same as `open-paxel dev`), unused reset aliases and wrappers.
