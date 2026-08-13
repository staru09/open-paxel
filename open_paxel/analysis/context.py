from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]
StepFn = Callable[[str], None]
OpenAICallFn = Callable[["OpenAICallRecord"], None]

_progress_fn: ContextVar[ProgressFn | None] = ContextVar("progress_fn", default=None)
_step_fn: ContextVar[StepFn | None] = ContextVar("step_fn", default=None)
_openai_call_fn: ContextVar[OpenAICallFn | None] = ContextVar("openai_call_fn", default=None)


@dataclass
class OpenAICallRecord:
    phase: str
    model: str
    status: str  # started | completed | failed
    duration_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    request_id: str | None = None
    detail: str | None = None
    chunk_index: int | None = None
    chunk_total: int | None = None


@dataclass
class AnalysisJobContext:
    """Thread/async-safe hooks for job progress and OpenAI telemetry."""

    log_progress: ProgressFn | None = None
    set_step: StepFn | None = None
    on_openai_call: OpenAICallFn | None = None
    _tokens: list[Any] = field(default_factory=list)

    def __enter__(self) -> AnalysisJobContext:
        if self.log_progress:
            self._tokens.append((_progress_fn, _progress_fn.set(self.log_progress)))
        if self.set_step:
            self._tokens.append((_step_fn, _step_fn.set(self.set_step)))
        if self.on_openai_call:
            self._tokens.append((_openai_call_fn, _openai_call_fn.set(self.on_openai_call)))
        return self

    def __exit__(self, *args) -> None:
        for var, token in reversed(self._tokens):
            var.reset(token)
        self._tokens.clear()


def emit_progress(message: str) -> None:
    fn = _progress_fn.get()
    if fn:
        fn(message)


def emit_step(step: str) -> None:
    fn = _step_fn.get()
    if fn:
        fn(step)


def emit_openai_call(record: OpenAICallRecord) -> None:
    logger.info(
        "openai phase=%s model=%s status=%s duration_ms=%s tokens=%s",
        record.phase,
        record.model,
        record.status,
        record.duration_ms,
        record.total_tokens,
    )
    fn = _openai_call_fn.get()
    if fn:
        fn(record)


def usage_from_completion(completion: Any) -> tuple[int | None, int | None, int | None, str | None]:
    usage = getattr(completion, "usage", None)
    if not usage:
        return None, None, None, getattr(completion, "id", None)
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
        getattr(usage, "total_tokens", None),
        getattr(completion, "id", None),
    )


def format_openai_log(record: OpenAICallRecord) -> str:
    if record.status == "started":
        parts = [f"OpenAI → {record.phase} ({record.model})"]
        if record.chunk_index and record.chunk_total:
            parts.append(f"chunk {record.chunk_index}/{record.chunk_total}")
        if record.detail:
            parts.append(record.detail)
        return " ".join(parts)

    token_bit = ""
    if record.total_tokens is not None:
        token_bit = (
            f" tokens: {record.prompt_tokens or 0} prompt + "
            f"{record.completion_tokens or 0} completion = {record.total_tokens} total"
        )
    req = f" id={record.request_id}" if record.request_id else ""
    if record.status == "failed":
        return f"OpenAI ✗ {record.phase} failed ({record.duration_ms}ms): {record.detail or 'error'}"
    return f"OpenAI ✓ {record.phase} done in {record.duration_ms}ms{token_bit}{req}"
