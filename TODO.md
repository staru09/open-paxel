# TODO

Findings from the codebase review (2026-10-05), ordered by priority.

## P0 — Privacy and data-loss bugs

- [ ] **Redact transcripts before condensing.** `pipeline/analysis.py` passes raw
  `read_full_transcript()` output (full JSONL, tool outputs, file contents) into
  `condense_transcript()`. `chunk_summary_user_prompt()` embeds chunks unredacted;
  `redact_text` only runs on the dry-run path. Fix: `redact_text(full_text, max_len=…)`
  once in `analysis.py` before condensing.
- [ ] **Broaden secret patterns** in `redact/transcript.py`. Currently not redacted:
  `sk-ant-api03-…` (Anthropic), `ghp_…`/`github_pat_…` (GitHub), `AKIA…` (AWS),
  JSON-style `"api_key": "…"`. Add a test with one sample per pattern.
- [ ] **Wire up or delete `redaction_level`** (`config.py`) — declared, never read.
- [ ] **Stop overwriting the enriched profile.** `save_report`, `update_report_title` and
  `create_upload` call `_refresh_profile_cache()`, which rebuilds a heuristic-only profile
  and overwrites the LLM narrative/episodes saved by `assemble_profile`. Renaming a session
  wipes paid-for LLM output. Fix: remove refresh from write paths; keep lazy build in
  `get_profile()` only.
- [ ] **Profile only reflects the latest batch.** `assemble_profile` takes episodes and
  episode dimensions from the current `PipelineContext` only; a second upload replaces
  earlier episodes. Persist episodes and aggregate across all uploads.
- [ ] **Keep a reference to background upload tasks** (`api/routes/uploads.py`).
  Bare `asyncio.create_task()` can be garbage-collected mid-run. Use a module-level set +
  `task.add_done_callback(set.discard)`.

## P1 — Discovery and tests

- [ ] **Read `cwd` from JSONL instead of decoding folder names.** Every record carries the
  real `cwd`. `discover_repos()` can read the first `cwd` from one session per folder,
  removing most of `decode_project_path` (only handles `C:`/`Z:`), path-fix and
  correction logic in `discover/scanner.py`.
- [ ] If the fingerprint stays: Claude's encoding is `re.sub(r"[^A-Za-z0-9]", "-", path)`;
  current `_claude_encoded_key` misses `.` (e.g. `my.app`, `~/.config`).
- [ ] **Fix 6 failing discovery tests on Linux/macOS** (`tests/test_paxel_pipeline.py`).
  They use `Path(r"Z:\…")`, which resolves under CWD on POSIX. Use `PureWindowsPath`,
  `skipif`, or delete with the item above.
- [ ] **Add CI**: GitHub Actions matrix (windows/macos/ubuntu) running `uv run pytest` and
  `uv run ruff check open_paxel tests`.
- [ ] `uv run ruff check --fix open_paxel tests` (27 errors, 23 auto-fixable).
- [ ] Replace `datetime.utcnow()` (10 call sites, 151 test warnings) with `datetime.now(UTC)`.

## P2 — Performance and robustness

- [ ] Per-report profile rebuild is O(batch × total sessions) — resolved by the P0 cache fix.
- [ ] `git/reader.py:code_quality_label` globs `**/test_*.py` through `node_modules`/`.venv`.
  Use `git ls-files`. "`pyproject.toml` exists" is a weak linter signal.
- [ ] Upload size cap in `api/routes/uploads.py` (files read fully into memory).
- [ ] Remove empty step 5 in `pipeline/orchestrator.py` (or give it real work).

## P3 — Repo hygiene

- [ ] Delete root `package-lock.json` (empty stub).
- [ ] Untrack `frontend/tsconfig.tsbuildinfo`; add to `.gitignore`.
- [ ] Drop unused `anthropic` optional extra from `pyproject.toml`.
- [ ] Dedupe dev deps (`[project.optional-dependencies].dev` vs `[dependency-groups].dev`).
- [ ] Reformat `redact/excerpts.py` (blank line after every line).
