"""Error monitoring setup — Sentry SDK wired to BugSink DSN.

BugSink is a self-hosted error monitoring platform that is compatible with
the Sentry SDK. Set SENTRY_DSN in .env to the DSN from your BugSink instance
(e.g. https://bugsink.ketch.media).

If SENTRY_DSN is not set, monitoring is disabled and no errors are collected.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize the Sentry SDK if SENTRY_DSN is configured.

    Call once at app startup (in create_app).
    """
    from app.config import settings

    if not settings.sentry_dsn:
        logger.debug("SENTRY_DSN not set — error monitoring disabled")
        return

    try:
        import sentry_sdk  # noqa: PLC0415

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.environment,
            # Don't send PII (email addresses, user names) to BugSink
            send_default_pii=False,
        )
        logger.info(
            "Error monitoring enabled (env=%s dsn_host=%s)",
            settings.environment,
            settings.sentry_dsn.split("@")[-1].split("/")[0] if "@" in settings.sentry_dsn else "?",
        )
    except ImportError:
        logger.warning(
            "sentry-sdk not installed — install with: uv add sentry-sdk[fastapi]"
        )
