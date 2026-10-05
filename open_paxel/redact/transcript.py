from __future__ import annotations

import re
from pathlib import Path

from open_paxel.text.tokens import estimate_tokens

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),  # OpenAI, Anthropic (sk-ant-...), OpenRouter
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)[\"']?\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[a-zA-Z0-9._-]+"),
]


def redact_text(text: str, max_len: int | None = 800) -> str:
    """Mask secrets; truncate to ``max_len`` chars (``None`` = no truncation)."""
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    if max_len is not None and len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def read_full_transcript(facts) -> str:
    """Return the session text, with secrets redacted."""
    return redact_text(_read_full_transcript(facts), max_len=None)


def _read_full_transcript(facts) -> str:
    parts = [m.text for m in facts.user_messages]
    if facts.assistant_text_chars:
        parts.append("[assistant output omitted from structured export]")
    joined = "\n\n".join(parts)
    if facts.transcript_path:
        try:
            raw = Path(facts.transcript_path).read_text(encoding="utf-8")
        except OSError:
            raw = ""
        if not facts.is_structured and raw.strip():
            return raw
        if facts.is_structured and estimate_tokens(raw) > estimate_tokens(joined):
            return raw
    return joined
