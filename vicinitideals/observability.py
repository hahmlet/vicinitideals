"""Shared observability helpers for API requests and pipeline runs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

TRACE_HEADER = "X-Trace-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def new_trace_id(candidate: str | None = None) -> str:
    trace_id = (candidate or "").strip()
    return trace_id or str(uuid4())


def begin_observation(candidate: str | None = None) -> tuple[str, datetime, float]:
    return new_trace_id(candidate), utc_now(), perf_counter()


def elapsed_ms(started_at_monotonic: float) -> int:
    return max(int((perf_counter() - started_at_monotonic) * 1000), 0)


def build_observability_payload(
    *,
    trace_id: str,
    started_at: datetime,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trace_id": trace_id,
        "started_at": format_timestamp(started_at),
    }
    if completed_at is not None:
        payload["completed_at"] = format_timestamp(completed_at)
    if duration_ms is not None:
        payload["duration_ms"] = max(int(duration_ms), 0)

    for key, value in extra.items():
        if value is not None:
            payload[key] = value

    return payload


def log_observation(logger: logging.Logger, event: str, **fields: Any) -> None:
    normalized = {key: value for key, value in fields.items() if value is not None}
    field_text = " ".join(f"{key}={normalized[key]}" for key in sorted(normalized))
    logger.info(
        "%s%s",
        event,
        f" {field_text}" if field_text else "",
        extra={"event": event, **normalized},
    )
