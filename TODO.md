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

## P4 — Support other coding agents (plugins + parsers)

Researched 2026-10-05 from official docs and source. Formats are mostly internal and change
often; items marked *unverified* need a check on a real install before building.

### Shared groundwork (do first)

- [ ] **Parser per agent** behind `parser/auto.py`; add `source_agent` to `SessionFacts`.
  Other agents don't record lines added/removed. Get them from edit/patch tool arguments,
  or from git through the existing commit linking.
- [ ] **One hook entrypoint**: `open-paxel hook <agent>`. It reads the hook's stdin JSON and
  accepts `transcript_path`, `transcriptPath` or `session_id`. Then it picks the parser and
  runs `analyze --async`. Today's `--transcript-from-stdin` only handles Claude's payload.
- [ ] **Dedupe per-turn hooks** (Windsurf, Amp, Copilot `agentStop`, Kiro `Stop`): re-analyze a
  session only when its transcript has changed, keyed by session/thread id + mtime.
- [ ] **`open-paxel mcp`**: an MCP server with `get_profile` / `analyze_session` tools. Every
  agent below except Aider supports MCP (Aider unverified), so this is the only way to ask
  "show my profile" from inside all of them.
- [ ] **Per-agent discovery and bulk import**: `open-paxel upload --agent codex` etc. for
  existing history, using the storage paths below.

### Tier 1 — Claude-style hooks that give a transcript path

| Agent | Hook | Package as | Transcript to parse |
|-------|------|------------|---------------------|
| Codex CLI | `SessionEnd` (`transcript_path` may be null → fall back to `session_id`) | `.codex-plugin/plugin.json` + `hooks/hooks.json`; marketplace `.agents/plugins/marketplace.json` | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — `session_meta` has cwd + git, `function_call`/`_output` pairs, `token_count` events |
| Gemini CLI | `SessionEnd` (`transcript_path`, `session_id`, `cwd`) | extension: `gemini-extension.json` + `hooks/hooks.json` + `commands/paxel.toml`; `gemini extensions install <repo>` | `~/.gemini/tmp/<hash>/chats/session-*.jsonl` (`.json` before Feb 2026); `toolCalls`, `tokens`, `model` per message |
| Copilot CLI | `agentStop` (`transcriptPath`); `sessionEnd` has no path | root `plugin.json`; `copilot plugin install`; or `~/.copilot/hooks/*.json` | `~/.copilot/session-state/<id>/events.jsonl` — `session.start.context.cwd`, `tool.execution_*` |
| Continue (`cn` CLI) | `SessionEnd` (Claude-compatible; *undocumented*, verified in source) | `.continue/settings.json`; also reads `~/.claude/settings.json`, so our Claude hook may already fire | `~/.continue/sessions/<id>.json` — `workspaceDirectory`, `toolCallStates`, `usage` |
| Cursor IDE | `sessionEnd` (camelCase events, common `transcript_path`); not for Cloud agents | `.cursor-plugin/plugin.json` or `~/.cursor/hooks.json` (`"version": 1`) | hook path, else `state.vscdb` `cursorDiskKV` (`composerData:*`, `bubbleId:*`) — SQLite, internal |

### Tier 2 — possible, but more work

- [ ] **OpenCode**: JS/TS plugin in `.opencode/plugins/` on `session.idle` (`sessionID` only).
  It would run `opencode export <id>` (output format *unverified*), or read
  `~/.local/share/opencode/opencode.db` (`session.directory`, `message`, `part` tables).
- [ ] **Windsurf / Devin Desktop**: `post_cascade_response_with_transcript` fires on every
  turn and gives `tool_info.transcript_path` (JSONL, kept for the last 100). Stored `.pb`
  history is encrypted, so the hook is the only way to get transcripts.
- [ ] **Cline**: SDK plugin hooks (`afterRun`, `session_shutdown`) cover the CLI/SDK only, not
  the VS Code extension. For the extension, import `~/.cline/data/tasks/<id>/`
  (`api_conversation_history.json`, `ui_messages.json` for timestamps).
- [ ] **Amp**: TS plugin on `agent.end` (fires per prompt). It writes `event.messages` to a temp
  file, then analyzes it. Local thread files stopped 2026-03-31; history is on the server.
- [ ] **Kiro**: `.kiro/hooks/<id>.json` with a `Stop` trigger. The transcript location is
  *unverified* (IDE and CLI layouts differ).
- [ ] **Copilot in VS Code**: only a `Stop` hook (Preview), and the transcript is "not a stable
  API". Import `workspaceStorage/<h>/GitHub.copilot-chat/transcripts/*.jsonl` (1.137+) and
  `chatSessions/*.json` (older).

### Skip for now

- **Aider**: no hooks or plugins. Support only importing `.aider.chat.history.md` (sessions start
  with `# aider chat started at`, user turns are `####`; no model or token data).
- **Roo Code**: repo archived 2026-05-15.
- **cursor-agent CLI**: no hooks (reported not firing `hooks.json`). Import only, from
  `~/.cursor/projects/<slug>/agent-transcripts/*.jsonl`, which has no timestamps or tool outputs.

### References

- Claude Code hooks/plugins: https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/plugins-reference
- Codex: https://developers.openai.com/plugins/build/plugins, https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs
- Gemini CLI: https://geminicli.com/docs/hooks/reference/, https://geminicli.com/docs/extensions/reference/
- Cursor: https://cursor.com/docs/agent/hooks, https://cursor.com/docs/plugins
- Copilot: https://docs.github.com/en/copilot/reference/hooks-reference, https://code.visualstudio.com/docs/agents/reference/hooks-reference
- Windsurf: https://docs.devin.ai/desktop/cascade/hooks
- OpenCode: https://opencode.ai/docs/plugins/ · Amp: https://ampcode.com/docs/plugin-api · Kiro: https://kiro.dev/docs/hooks/types.md
- Cline: https://docs.cline.bot/sdk/plugins · Aider: https://aider.chat/docs/config/options.html
- Existing parsers to learn from: agentgrep (https://agentgrep.org/backends/), ccusage
  (https://github.com/ccusage/ccusage), deja-vu (https://github.com/vshulcz/deja-vu)

## Research — minimum session data for a stable profile

**Question:** what is the smallest slice of a session that gives the same profile as the
full transcript? Hypothesis: we need every user message, but can drop most of the
model's side.

**Why it matters:**
- Today the LLM gets the raw JSONL (`redact/transcript.py:read_full_transcript`), which is
  mostly tool outputs, file contents and JSON syntax.
- Above 12 × 120k chars the condenser samples chunks, so a 1M-token session drops roughly
  65% or more of its content, user messages included.
- Every other agent stores different fields, so knowing the minimum also tells us what
  each new parser must extract.
- Less input also means less cost, fewer chunks and less data leaving the machine.

**Where the signals come from today:**
- Heuristics use user messages, tool *counts* (Read/Grep/Write/Edit/Bash), plan-mode
  entries, agent runs, tool errors, test/lint commands, lines changed and timestamps. They
  never use assistant prose or tool outputs.
- The LLM dimensions (steering, execution, engineering, product_instinct, planning) are
  judged on user behavior. The model's side is context for what the user was reacting to.

### Experiment

- [ ] **Dataset.** 30+ Claude Code sessions: short, medium, and at least 5 over 200k tokens.
  Also 3+ users' full histories, for the profile-level checks.
- [ ] **Input levels** (each one adds to the one before):
  - **L0:** metadata only. Heuristics, no LLM.
  - **L1:** all user messages, verbatim, with timestamps.
  - **L2:** + tool calls as one line each: name, short args (file path, command), and an
    error/success flag. No outputs.
  - **L3:** + assistant text cut down. Variants: only the assistant message right before
    each user turn, or the first and last N chars of each assistant turn.
  - **L4:** + tool outputs cut to 1–2 lines (error messages kept in full).
  - **L5 (reference):** the full transcript with no chunk sampling. Use a long-context
    model, or set `condense_max_chunks` high enough to cover everything.
- [ ] **Noise floor.** Run L5 three times per session. Any level whose difference from L5
  stays inside that run-to-run variance counts as "the same profile".
- [ ] **Session-level metrics, per level vs L5:**
  - difference in each dimension score
  - archetype agreement
  - Jaccard overlap of decision patterns from `decision_classifier`
  - narrative agreement (LLM-judge)
  - input tokens, cost and latency
- [ ] **Profile-level metrics.**
  - Rebuild each test user's profile from every level.
  - Bootstrap over subsets of sessions to find how many sessions it takes before every
    dimension stays within ±5 points. That's the minimum number of sessions for a
    stable profile.
- [ ] **Specific checks:**
  - Can steering be judged without the assistant message the user was answering? (L1 vs L3)
  - Do engineering and execution need test output, or is "a test command ran and
    passed/failed" enough? (L2 vs L4)
  - Are thinking blocks, file-history snapshots and duplicated `toolUseResult` content
    ever useful?

### Deliverables

- [ ] Short results write-up: the chosen level, per-dimension differences, and cost savings.
- [ ] A `render_compact_transcript(facts)` function at the chosen level. It replaces raw JSONL
  as the LLM input in `read_full_transcript`. If most sessions then fit in a few chunks,
  chunk sampling and its data loss go away.
- [ ] A list of the minimum fields each parser must provide (feeds P4).
- [ ] A minimum session count before a profile is shown as stable (e.g. a "low confidence"
  badge below it).

## Also fixed during the refactor

- [x] `openai_api_key` in `config.toml` (written by `init-config`) was ignored: aliased fields
  need `populate_by_name`. Env vars now override `config.toml`, as the README says.
- [x] Circular import: importing `open_paxel.scorer` first failed. Removed unused package
  re-exports from `__init__.py` files.
- [x] One `SQLiteRepository` per CLI command (upload opened a new engine per session).
- [x] Replaced the hand-rolled TOML parser with stdlib `tomllib`; removed `dev.py`
  (same as `open-paxel dev`), unused reset aliases and wrappers.
