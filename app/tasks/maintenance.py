"""Maintenance Celery tasks — scheduled housekeeping that keeps the DB tidy.

``purge_test_deals_task`` runs daily and hard-deletes accumulated E2E /
regression **test deals** (anything the Hide-Test filter hides), so the
Opportunities views and the database don't fill back up with throwaway test
records. It is scoped strictly to the test-name pattern and age-guarded, so it
can never touch a real deal or an in-flight test run. See
:mod:`app.services.test_cleanup` for the match predicate and delete graph.
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger

from app.config import settings
from app.db import AsyncSessionLocal
from app.services.test_cleanup import purge_test_deals
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.maintenance.purge_test_deals_task", bind=True)
def purge_test_deals_task(self, dry_run: bool = False) -> dict[str, Any]:
    """Daily janitor: delete test deals older than the configured age guard."""
    del self
    return asyncio.run(_purge_test_deals(dry_run=dry_run))


async def _purge_test_deals(dry_run: bool = False) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await purge_test_deals(
            session,
            execute=not dry_run,
            max_age_hours=settings.test_deal_purge_min_age_hours,
        )
    logger.info(
        "purge_test_deals: matched=%s total_rows=%s executed=%s (min_age_h=%s)",
        result["matched"],
        result["total_rows"],
        result["executed"],
        settings.test_deal_purge_min_age_hours,
    )
    return result
