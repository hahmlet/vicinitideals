"""The monthly county-source check -- the one automated piece of the county copy.

Steph's condition on keeping the screen's copy of the county map in this
database (HUMAN_TODO 20, 2026-09-19): no automated connection unless there
is a failure-state warning. This task is that connection, and it can only
warn. Once a month it asks each source in ``flats/config/pipeline.yaml``
whether it is still what the copy in use was taken from and writes one
``flats.probes`` row; the Lots pages turn the newest row into a banner.
It downloads nothing and changes nothing in the copy. There is no refresh
task, and none is planned: a refresh is a person running the runbook.
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger

from app.db import AsyncSessionLocal
from app.services.flats_refresh import run_probe
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.flats_probe.flats_probe_task", bind=True)
def flats_probe_task(self) -> dict[str, Any]:
    """Monthly: probe every county source against the copy in use; write one row."""
    del self
    return asyncio.run(_probe())


async def _probe() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        row = await run_probe(session, log=logger.info)
        await session.commit()
        summary = {
            "probe_id": row.id,
            "status": row.status,
            "findings": len(row.findings),
            "not_ok": [f for f in row.findings if f["finding"] != "ok"],
            "seconds": float(row.seconds) if row.seconds is not None else None,
        }
    logger.info("flats_probe: %s (%s findings, %s not ok)", row.status, len(row.findings), len(summary["not_ok"]))
    return summary
