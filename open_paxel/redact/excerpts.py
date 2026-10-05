from __future__ import annotations


from open_paxel.models.domain import RedactedExcerpt

from open_paxel.parser.patterns import REDIRECT_PATTERN

from open_paxel.redact.transcript import read_full_transcript, redact_text

from open_paxel.text.chunking import MAX_SESSION_TRANSCRIPT_CHARS

from open_paxel.text.tokens import estimate_tokens


def build_excerpts(facts, metrics) -> RedactedExcerpt:

    first = facts.user_messages[0].text if facts.user_messages else ""

    steering: list[str] = []

    for msg in facts.user_messages:
        if REDIRECT_PATTERN.search(msg.text) or len(msg.text) < 120:
            steering.append(redact_text(msg.text, 400))

        if len(steering) >= 3:
            break

    edits = []

    if facts.files_edited:
        edits.append(
            f"Edited {facts.files_edited} files (+{facts.lines_added}/-{facts.lines_removed} lines)"
        )

    if facts.agent_runs:
        edits.append(f"Spawned {facts.agent_runs} agent run(s)")

    if facts.tool_counts.get("CodeBlock"):
        edits.append(f"{facts.tool_counts['CodeBlock']} code block(s) in session")

    outcome = facts.title or "Session completed"

    if facts.user_messages:
        outcome = redact_text(facts.user_messages[-1].text, 300)

    full_text = read_full_transcript(facts)

    transcript_tokens = estimate_tokens(full_text)

    truncated = len(full_text) > MAX_SESSION_TRANSCRIPT_CHARS

    raw_transcript = redact_text(full_text, max_len=MAX_SESSION_TRANSCRIPT_CHARS)

    return RedactedExcerpt(
        session_id=facts.session_id,
        first_prompt=redact_text(first, 500),
        steering_moments=steering,
        edit_summaries=edits,
        outcome_summary=outcome,
        raw_transcript=raw_transcript,
        accumulated_summary="",
        chunk_count=0,
        metrics_json={
            "steering_heuristic": metrics.steering,
            "execution_heuristic": metrics.execution,
            "tool_counts": facts.tool_counts,
            "duration_ms": facts.duration_ms,
            "total_tokens": facts.total_tokens,
            "transcript_tokens": transcript_tokens,
            "is_structured": facts.is_structured,
            "source_format": facts.source_format,
            "uses_full_transcript": True,
            "transcript_truncated": truncated,
        },
    )
