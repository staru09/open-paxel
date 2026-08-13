from __future__ import annotations

import hashlib
from pathlib import Path

from open_paxel.models.domain import SessionFacts, UserMessage
from open_paxel.parser.patterns import (
    CAPS_FRUSTRATION,
    QUESTION_PATTERN,
    REDIRECT_PATTERN,
    TEST_LINT_PATTERN,
    THANK_PATTERN,
    FRONTMATTER,
    H1_TITLE,
    TURN_HEADER,
    TURN_INLINE,
)
from open_paxel.text.document_scan import DocumentStats, scan_document
from open_paxel.text.tokens import chunk_paragraphs

USER_ROLES = frozenset({"user", "human", "you"})
ASSISTANT_ROLES = frozenset({"assistant", "ai", "claude", "model"})


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return meta, text[match.end() :]


def _normalize_role(label: str) -> str:
    key = label.strip().lower()
    if key in USER_ROLES:
        return "user"
    if key in ASSISTANT_ROLES:
        return "assistant"
    return "system"


def _split_labeled_turns(body: str) -> list[tuple[str, str]] | None:
    """Return turns if explicit User/Assistant labels exist."""
    turns: list[tuple[str, str]] = []

    header_matches = list(TURN_HEADER.finditer(body))
    if header_matches:
        for i, match in enumerate(header_matches):
            role = _normalize_role(match.group(1))
            start = match.end()
            end = header_matches[i + 1].start() if i + 1 < len(header_matches) else len(body)
            text = body[start:end].strip()
            if text and role != "system":
                turns.append((role, text))
        if turns:
            return turns

    inline_parts = TURN_INLINE.split(body)
    if len(inline_parts) > 1:
        i = 1
        while i + 1 < len(inline_parts):
            role = _normalize_role(inline_parts[i])
            text = inline_parts[i + 1].strip()
            if text and role != "system":
                turns.append((role, text))
            i += 2
        if turns:
            return turns

    return None


def _messages_from_turns(turns: list[tuple[str, str]]) -> tuple[list[UserMessage], int]:
    user_messages: list[UserMessage] = []
    assistant_chars = 0
    for role, text in turns:
        if role == "user":
            user_messages.append(
                UserMessage(text=text, word_count=len(text.split()))
            )
        else:
            assistant_chars += len(text)
    return user_messages, assistant_chars


def _messages_from_chunks(body: str) -> tuple[list[UserMessage], int]:
    """Unstructured docs: paragraph/token chunks instead of guessed roles."""
    segments = chunk_paragraphs(body, target_tokens=400)
    user_messages = [
        UserMessage(text=seg, word_count=len(seg.split())) for seg in segments
    ]
    # Remaining prose not in first-pass chunks counts as assistant-ish volume
    assistant_chars = max(0, len(body) - sum(len(m.text) for m in user_messages))
    return user_messages, assistant_chars


def _extract_title(body: str, meta: dict[str, str], path: Path) -> str | None:
    for key in ("title", "name", "subject"):
        if meta.get(key):
            return meta[key]
    h1 = H1_TITLE.search(body)
    if h1:
        return h1.group(1).strip()
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    if first_line and len(first_line) <= 120 and not first_line.startswith("#"):
        return first_line
    return path.stem


def _session_id(path: Path, content: str, meta: dict[str, str]) -> str:
    for key in ("sessionid", "session_id", "id"):
        if meta.get(key):
            return meta[key]
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"import-{digest}"


def _per_message_hits(user_messages: list[UserMessage]) -> tuple[int, int, int, int]:
    redirect = question = thank = caps = 0
    for msg in user_messages:
        if REDIRECT_PATTERN.search(msg.text):
            redirect += 1
        if QUESTION_PATTERN.search(msg.text):
            question += 1
        if THANK_PATTERN.search(msg.text):
            thank += 1
        if CAPS_FRUSTRATION.search(msg.text):
            caps += 1
    return redirect, question, thank, caps


def _apply_document_stats(
    facts_kwargs: dict,
    doc: DocumentStats,
    *,
    structured: bool,
    user_messages: list[UserMessage],
) -> None:
    """Prefer document-level counts for unstructured uploads."""
    if structured:
        return

    msg_redirect, msg_question, msg_thank, msg_caps = _per_message_hits(user_messages)
    facts_kwargs["redirect_hits"] = max(doc.redirect_hits, msg_redirect)
    facts_kwargs["question_prompts"] = max(doc.question_hits, msg_question)
    facts_kwargs["thank_you_count"] = max(doc.thank_you_hits, msg_thank)
    facts_kwargs["caps_frustration_hits"] = max(doc.caps_frustration_hits, msg_caps)
    facts_kwargs["test_lint_runs"] = doc.test_lint_hits
    facts_kwargs["lines_added"] = doc.diff_lines_added
    facts_kwargs["lines_removed"] = doc.diff_lines_removed
    facts_kwargs["files_edited"] = max(
        facts_kwargs.get("files_edited", 0),
        doc.file_path_mentions,
        doc.code_block_count,
    )
    facts_kwargs["tool_counts"] = {
        **facts_kwargs.get("tool_counts", {}),
        **({"Bash": doc.bash_block_count} if doc.bash_block_count else {}),
        **({"CodeBlock": doc.code_block_count} if doc.code_block_count else {}),
    }
    facts_kwargs["raw_turn_count"] = max(
        len(user_messages),
        doc.estimated_turns,
    )
    if doc.plan_hits and facts_kwargs.get("plan_mode_entries", 0) == 0:
        facts_kwargs["plan_mode_entries"] = min(doc.plan_hits, 5)
    if doc.error_hits:
        facts_kwargs["tool_errors"] = min(doc.error_hits, 20)


class TextSessionParser:
    """Parse plain-text or markdown exports using token-aware document analysis."""

    def parse(self, path: Path) -> SessionFacts:
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        doc = scan_document(body)
        suffix = path.suffix.lower()
        source_format = "markdown" if suffix in (".md", ".markdown") else "text"

        labeled = _split_labeled_turns(body)
        structured = labeled is not None and len(labeled) >= 2

        if structured and labeled:
            user_messages, assistant_chars = _messages_from_turns(labeled)
        else:
            user_messages, assistant_chars = _messages_from_chunks(body)

        redirect, question, thank, caps = _per_message_hits(user_messages)

        tool_counts: dict[str, int] = {}
        if doc.bash_block_count:
            tool_counts["Bash"] = doc.bash_block_count
        if doc.code_block_count:
            tool_counts["CodeBlock"] = doc.code_block_count

        facts_kwargs: dict = dict(
            session_id=_session_id(path, raw, meta),
            transcript_path=str(path),
            project_path=meta.get("project") or meta.get("cwd"),
            title=_extract_title(body, meta, path),
            git_branch=meta.get("gitbranch") or meta.get("git_branch"),
            user_messages=user_messages,
            assistant_text_chars=assistant_chars,
            tool_counts=tool_counts,
            lines_added=doc.diff_lines_added,
            lines_removed=doc.diff_lines_removed,
            files_edited=max(doc.file_path_mentions, doc.code_block_count),
            test_lint_runs=doc.test_lint_hits if not structured else len(
                TEST_LINT_PATTERN.findall(body)
            ),
            redirect_hits=redirect if structured else doc.redirect_hits,
            question_prompts=question if structured else doc.question_hits,
            thank_you_count=thank if structured else doc.thank_you_hits,
            caps_frustration_hits=caps if structured else doc.caps_frustration_hits,
            raw_turn_count=len(user_messages) if structured else doc.estimated_turns,
            total_tokens=doc.total_tokens,
            source_format=source_format,
            is_structured=structured,
        )

        _apply_document_stats(facts_kwargs, doc, structured=structured, user_messages=user_messages)

        return SessionFacts(**facts_kwargs)
