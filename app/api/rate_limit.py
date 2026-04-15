"""Lightweight Redis-backed rate limiter.

Fixed-window counters with automatic TTL expiry.  Intended for light-weight
abuse prevention on public endpoints (e.g. /forgot-password) — NOT for
fine-grained API quotas.

Usage:
    allowed = await check_rate_limit(
        key="forgot_pw:ip:203.0.113.5",
        max_count=5,
        window_seconds=900,  # 15 min
    )
    if not allowed:
        return 429 response

Design decisions:
- Fail-open: if Redis is unreachable, allow the request rather than
  blocking legitimate users.  We log a warning so the ops team notices.
- Fixed window (not sliding): cheap one-INCR-plus-conditional-EXPIRE
  operation.  Sliding windows would need sorted sets or Lua scripts —
  overkill for a password-reset form.
- The client is created lazily and cached on the module for the life of
  the worker process.  Redis.asyncio clients are connection-pooled so
  sharing is safe.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None


def _get_client() -> Any:
    """Lazy-init the async Redis client, cached at module scope."""
    global _client
    if _client is None:
        try:
            import redis.asyncio as redis  # type: ignore
            _client = redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover — dev environments without redis
            logger.warning("Redis client init failed: %s (rate limiter fails open)", exc)
            _client = False  # sentinel: tried and failed
    return _client


async def check_rate_limit(
    key: str,
    max_count: int,
    window_seconds: int,
) -> bool:
    """Increment a counter and return True if the request is allowed.

    Fails open: if Redis is unreachable, allow the request (logged as a
    warning).  Better to serve one request too many than to lock out
    legitimate users because the broker is down.
    """
    client = _get_client()
    if not client:
        return True  # fail-open: redis not available

    try:
        count = await client.incr(key)
        if count == 1:
            # First hit in this window — set the expiry
            await client.expire(key, window_seconds)
        return count <= max_count
    except Exception as exc:
        logger.warning("Rate limit check failed for %s: %s (fail-open)", key, exc)
        return True
