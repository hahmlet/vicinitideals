"""What a request answers when the background-job queue cannot be reached.

Every "start a background job" route hands work to Celery through the Redis
broker (``.delay`` / ``.apply_async`` / ``send_task``), and a few stash
payloads in the same Redis first. When Redis or the broker is down those calls
raise a kombu ``OperationalError`` or a redis ``ConnectionError``; left alone
that surfaces as a raw 500. Routes that leave a row behind (an export job, an
inbound email, a broker marked "pending") catch ``BROKER_ERRORS`` themselves
and undo it; everything else falls through to the app-wide handler registered
in ``app.api.main``, which logs the error and answers with
``queue_unavailable_response``.
"""

from __future__ import annotations

import logging
from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

QUEUE_UNAVAILABLE_MESSAGE = (
    "The background worker is not reachable right now; try again in a few minutes."
)

BROKER_ERRORS: tuple[type[Exception], ...] = (
    KombuOperationalError,
    RedisConnectionError,
    RedisTimeoutError,
)


def log_queue_unavailable(request: Request, exc: BaseException) -> None:
    logger.error(
        "background queue unreachable on %s %s: %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
    )


def queue_unavailable_response(request: Request) -> Response:
    """HTMX gets a fragment it will swap (htmx 2 drops 5xx bodies silently);
    everything else gets a JSON 503 in the app's error envelope, with the
    sentence also under ``error`` for the fetch() callers that read that key."""
    if request.headers.get("HX-Request"):
        return HTMLResponse(
            '<div class="alert alert-warning" role="alert" data-queue-unavailable>'
            f"{escape(QUEUE_UNAVAILABLE_MESSAGE)}</div>",
            status_code=200,
        )
    return JSONResponse(
        status_code=503,
        content={
            "code": "queue_unavailable",
            "message": QUEUE_UNAVAILABLE_MESSAGE,
            "detail": None,
            "error": QUEUE_UNAVAILABLE_MESSAGE,
        },
    )


__all__ = [
    "BROKER_ERRORS",
    "QUEUE_UNAVAILABLE_MESSAGE",
    "log_queue_unavailable",
    "queue_unavailable_response",
]
