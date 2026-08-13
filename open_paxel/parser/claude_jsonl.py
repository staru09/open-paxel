from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from open_paxel.models.domain import SessionFacts, UserMessage
from open_paxel.parser.patterns import (
    CAPS_FRUSTRATION,
    QUESTION_PATTERN,
    REDIRECT_PATTERN,
    TEST_LINT_PATTERN,
    THANK_PATTERN,
)
from open_paxel.parser.filters import apply_filter_stats, is_local_shell_command
from open_paxel.text.tokens import estimate_tokens


def decode_project_path(encoded: str) -> str:
    """Decode Claude Code project folder name to path."""
    if len(encoded) >= 4 and encoded[1:3] == "--" and encoded[0].isalpha():
        drive = encoded[0].upper()
        rest = encoded[3:]
        return f"{drive}:\\" + rest.replace("-", "\\")
    return encoded.replace("-", "/")



class ClaudeCodeJsonlParser:
    def parse(self, path: Path) -> SessionFacts:
        path = Path(path)
        records: list[dict] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        session_id = path.stem
        project_path: str | None = None
        title: str | None = None
        git_branch: str | None = None
        models: list[str] = []
        user_messages: list[UserMessage] = []
        assistant_chars = 0
        tool_counts: dict[str, int] = {}
        lines_added = 0
        lines_removed = 0
        files_edited = 0
        plan_entries = 0
        plan_exits = 0
        agent_runs = 0
        max_agent_ms = 0
        tool_errors = 0
        redirect_hits = 0
        question_prompts = 0
        thank_you = 0
        caps_hits = 0
        test_lint = 0
        timestamps: list[datetime] = []
        raw_turn_count = 0

        local_commands_removed = 0
        tool_only_turns_removed = 0

        for rec in records:
            rtype = rec.get("type")
            if rtype == "ai-title":
                title = rec.get("aiTitle") or title
            ts = rec.get("timestamp")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except ValueError:
                    pass

            cwd = rec.get("cwd")
            if cwd and not project_path:
                project_path = cwd
            if rec.get("gitBranch"):
                git_branch = rec["gitBranch"]
            if rec.get("sessionId"):
                session_id = rec["sessionId"]

            if rtype == "user":
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    msg = {}
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                    raw_turn_count += 1
                    wc = len(text.split())
                    user_messages.append(
                        UserMessage(
                            text=text,
                            timestamp=timestamps[-1] if timestamps else None,
                            word_count=wc,
                        )
                    )
                    if REDIRECT_PATTERN.search(text):
                        redirect_hits += 1
                    if QUESTION_PATTERN.search(text):
                        question_prompts += 1
                    if THANK_PATTERN.search(text):
                        thank_you += 1
                    if CAPS_FRUSTRATION.search(text):
                        caps_hits += 1
                elif isinstance(content, list):
                    tool_only_turns_removed += 1
                    for block in content:
                        if isinstance(block, dict) and block.get("is_error"):
                            tool_errors += 1

            elif rtype == "assistant":
                message = rec.get("message")
                if not isinstance(message, dict):
                    message = {}
                model = message.get("model")
                if model:
                    models.append(model)
                content = message.get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            assistant_chars += len(block.get("text") or "")
                        elif btype == "tool_use":
                            name = block.get("name") or "unknown"
                            tool_counts[name] = tool_counts.get(name, 0) + 1
                            inp = block.get("input")
                            if not isinstance(inp, dict):
                                inp = {}
                            if name in ("Write", "Edit"):
                                files_edited += 1
                            if name == "EnterPlanMode":
                                plan_entries += 1
                            if name == "ExitPlanMode":
                                plan_exits += 1
                            if name == "Agent":
                                agent_runs += 1
                            if name == "Bash":
                                cmd = str(inp.get("command") or "")
                                if is_local_shell_command(cmd):
                                    local_commands_removed += 1
                                if TEST_LINT_PATTERN.search(cmd):
                                    test_lint += 1

            # tool result with toolStats from Agent (toolUseResult may be dict or error string)
            if rtype == "user":
                tr = rec.get("toolUseResult")
                if isinstance(tr, dict):
                    stats = tr.get("toolStats")
                    if not isinstance(stats, dict):
                        stats = {}
                    lines_added += int(stats.get("linesAdded") or 0)
                    lines_removed += int(stats.get("linesRemoved") or 0)
                    files_edited += int(stats.get("editFileCount") or 0)
                    dur = int(tr.get("totalDurationMs") or 0)
                    if dur > max_agent_ms:
                        max_agent_ms = dur

        duration_ms = 0
        started_at = timestamps[0] if timestamps else None
        ended_at = timestamps[-1] if timestamps else None
        if started_at and ended_at:
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)

        full_text = " ".join(m.text for m in user_messages)
        total_tokens = estimate_tokens(full_text) + estimate_tokens("x" * assistant_chars)

        filter_stats = apply_filter_stats(
            local_commands_removed=local_commands_removed,
            tool_only_turns_removed=tool_only_turns_removed,
        )
        analyzable = raw_turn_count > 0 or bool(title)

        return SessionFacts(
            session_id=session_id,
            transcript_path=str(path),
            project_path=project_path,
            title=title,
            git_branch=git_branch,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            models_used=models,
            user_messages=user_messages,
            assistant_text_chars=assistant_chars,
            tool_counts=tool_counts,
            lines_added=lines_added,
            lines_removed=lines_removed,
            files_edited=files_edited,
            plan_mode_entries=plan_entries,
            plan_mode_exits=plan_exits,
            agent_runs=agent_runs,
            max_agent_duration_ms=max_agent_ms,
            tool_errors=tool_errors,
            redirect_hits=redirect_hits,
            question_prompts=question_prompts,
            thank_you_count=thank_you,
            caps_frustration_hits=caps_hits,
            test_lint_runs=test_lint,
            raw_turn_count=raw_turn_count,
            total_tokens=total_tokens,
            source_format="jsonl",
            is_structured=True,
            analyzable=analyzable,
            filter_stats=filter_stats,
        )
