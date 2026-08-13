from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from open_paxel.analysis.context import (
    OpenAICallRecord,
    emit_openai_call,
    emit_step,
    format_openai_log,
    usage_from_completion,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def tracked_openai_call(
    *,
    phase: str,
    model: str,
    call: Callable[[], Awaitable[T]],
    chunk_index: int | None = None,
    chunk_total: int | None = None,
    detail: str | None = None,
) -> T:
    started = OpenAICallRecord(
        phase=phase,
        model=model,
        status="started",
        chunk_index=chunk_index,
        chunk_total=chunk_total,
        detail=detail,
    )
    emit_openai_call(started)
    emit_step(format_openai_log(started))

    t0 = time.monotonic()
    try:
        result = await call()
        duration_ms = int((time.monotonic() - t0) * 1000)
        prompt_t, completion_t, total_t, req_id = usage_from_completion(result)
        completed = OpenAICallRecord(
            phase=phase,
            model=model,
            status="completed",
            duration_ms=duration_ms,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
            request_id=req_id,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        emit_openai_call(completed)
        emit_step(format_openai_log(completed))
        return result
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        failed = OpenAICallRecord(
            phase=phase,
            model=model,
            status="failed",
            duration_ms=duration_ms,
            detail=str(exc),
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        emit_openai_call(failed)
        emit_step(format_openai_log(failed))
        logger.exception("OpenAI call failed phase=%s", phase)
        raise
