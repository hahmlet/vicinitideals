"""Nightly: bring the flag history in line with the run in use (FOLLOWUPS 37).

Steph's flag plan keeps every flag a lot has carried, with the run that
opened it and the run that cleared it. The screen writes flags into each
run; this task follows whichever run the Lots pages show -- after a
promotion, after a rollback, or neither -- through
:func:`app.services.flats_flags.sync_instances`, which is idempotent: on a
night nothing moved it opens and clears nothing. Then the nightly check
(:func:`app.services.flats_flags.nightly_check`) recolours every row under
today's rule set and writes the design sensitivity report. Neither changes a
lot result or a colour.
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger

from app.db import AsyncSessionLocal
from app.services.flats_flags import nightly_check, sync_instances
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.flats_flags.flats_flags_nightly_task", bind=True)
def flats_flags_nightly_task(self) -> dict[str, Any]:
    """Nightly: sync flag instances against the run in use."""
    del self
    return asyncio.run(_nightly())


async def _nightly() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        got = await sync_instances(session)
        await session.commit()
        checked = await nightly_check(session)
        await session.commit()
    summary = {
        "run_id": got.run_id,
        "opened": got.opened,
        "updated": got.updated,
        "cleared": got.cleared,
        "skipped": got.skipped,
        "check_ok": checked.ok,
        "check_rows": checked.report.get("rows", 0),
    }
    logger.info("flats_flags: %s", summary)
    return summary
