"""Listing ingestion trigger endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from vicinitideals.api.deps import CurrentUserId, DBSession
from vicinitideals.models.ingestion import IngestJob
from vicinitideals.models.realie_usage import RealieUsage
from vicinitideals.observability import format_timestamp, log_observation, new_trace_id, utc_now
from vicinitideals.scrapers.realie import RealieEnricher, _current_month
from vicinitideals.tasks.scraper import _scrape_crexi, scrape_crexi, scrape_loopnet

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)


class IngestTriggerRequest(BaseModel):
    source: Literal["loopnet", "crexi"] | None = None
    search_params: dict[str, Any] = Field(default_factory=dict)


def _queue_scrape_task(
    task: Any,
    *,
    default_prefix: str,
    kwargs: dict[str, Any],
) -> str:
    task_id = f"{default_prefix}-{uuid4()}"

    # Check if any Celery workers are actually available (ping with short timeout).
    # apply_async succeeds silently even with no workers when Redis broker is reachable,
    # so we must check for live workers explicitly before dispatching.
    try:
        workers = cast(Any, task).app.control.ping(timeout=0.5)
    except Exception:
        workers = []

    if workers:
        try:
            async_result = cast(Any, task).apply_async(kwargs=kwargs, queue="scraping")
            return async_result.id or task_id
        except Exception:
            pass

    # No live workers — run directly on the FastAPI event loop
    async def _run_and_log(**kw: Any) -> None:
        try:
            await _scrape_crexi(**kw)
        except Exception as exc:
            import traceback
            logging.getLogger(__name__).error("scrape_crexi background task failed: %s\n%s", exc, traceback.format_exc())
    asyncio.create_task(_run_and_log(**kwargs))
    return task_id


@router.post("/ingest/trigger")
async def trigger_ingest_job(
    http_request: Request,
    current_user_id: CurrentUserId,
    payload: IngestTriggerRequest | None = None,
) -> dict[str, str]:
    request = payload or IngestTriggerRequest()
    if request.source in (None, "loopnet"):
        # LoopNet ingest is intentionally disabled; Crexi remains active.
        request.source = "crexi"
    triggered_by = str(current_user_id)
    trace_id = new_trace_id(getattr(http_request.state, "trace_id", None))
    queued_at = utc_now()

    task_ids: list[str] = []
    if request.source in (None, "crexi"):
        task_ids.append(
            _queue_scrape_task(
                scrape_crexi,
                default_prefix="ingest-crexi",
                kwargs={"triggered_by": triggered_by, "trace_id": trace_id},
            )
        )

    task_id = ",".join(task_ids)
    log_observation(
        logger,
        "ingest_jobs_queued",
        trace_id=trace_id,
        triggered_by=triggered_by,
        source=request.source or "all",
        task_id=task_id,
    )
    return {
        "status": "queued",
        "task_id": task_id,
        "source": request.source or "all",
        "trace_id": trace_id,
        "queued_at": format_timestamp(queued_at),
    }


@router.get("/ingest/latest")
async def latest_ingest_job(session: DBSession) -> dict[str, Any]:
    """Return the most recent ingest job — used by the UI to poll scrape progress."""
    job = (await session.execute(
        select(IngestJob).order_by(IngestJob.started_at.desc()).limit(1)
    )).scalar_one_or_none()
    if job is None:
        return {"status": "idle"}
    return {
        "status": job.status,
        "source": job.source,
        "records_fetched": job.records_fetched,
        "records_new": job.records_new,
        "records_duplicate": job.records_duplicate_exact,
        "source_total": job.source_total,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


class ScrapeRunRequest(BaseModel):
    max_results: int | None = None


@router.post("/scraper/run")
async def run_crexi_scraper(
    http_request: Request,
    max_results: int | None = None,
) -> dict[str, str]:
    triggered_by = "ui"
    trace_id = new_trace_id(getattr(http_request.state, "trace_id", None))
    queued_at = utc_now()
    task_id = _queue_scrape_task(
        scrape_crexi,
        default_prefix="scrape-crexi",
        kwargs={
            "triggered_by": triggered_by,
            "trace_id": trace_id,
            **({"max_results": max_results} if max_results is not None else {}),
        },
    )
    log_observation(
        logger,
        "ingest_job_queued",
        trace_id=trace_id,
        triggered_by=triggered_by,
        source="crexi",
        task_id=task_id,
    )
    return {
        "status": "queued",
        "task_id": task_id,
        "source": "crexi",
        "trace_id": trace_id,
        "queued_at": format_timestamp(queued_at),
    }


# ---------------------------------------------------------------------------
# Realie.ai enrichment
# ---------------------------------------------------------------------------

@router.get("/realie/status")
async def realie_status(session: DBSession) -> dict[str, Any]:
    """Return current month's Realie call budget."""
    month = _current_month()
    result = await session.execute(
        select(RealieUsage).where(RealieUsage.month == month)
    )
    usage = result.scalar_one_or_none()
    if usage is None:
        return {
            "month": month,
            "calls_used": 0,
            "call_limit": 25,
            "calls_remaining": 25,
            "locked": False,
            "last_call_at": None,
        }
    return {
        "month": usage.month,
        "calls_used": usage.calls_used,
        "call_limit": usage.call_limit,
        "calls_remaining": usage.calls_remaining,
        "locked": usage.is_locked,
        "last_call_at": usage.last_call_at.isoformat() if usage.last_call_at else None,
    }


@router.post("/realie/enrich")
async def run_realie_enrichment(
    http_request: Request,
    session: DBSession,
) -> dict[str, Any]:
    """
    Trigger Realie.ai enrichment for all unenriched listings.
    Returns immediately; enrichment runs as a background task.
    Returns 429 if monthly quota is already exhausted.
    """
    from fastapi import HTTPException

    # Quick quota check before spawning
    month = _current_month()
    result = await session.execute(
        select(RealieUsage).where(RealieUsage.month == month)
    )
    usage = result.scalar_one_or_none()
    if usage is not None and usage.is_locked:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "realie_quota_exceeded",
                "calls_used": usage.calls_used,
                "call_limit": usage.call_limit,
                "month": usage.month,
            },
        )

    trace_id = new_trace_id(getattr(http_request.state, "trace_id", None))
    queued_at = utc_now()

    async def _run() -> None:
        from vicinitideals.db import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                enricher = RealieEnricher()
                summary = await enricher.enrich_batch(db)
                logger.warning(
                    "realie_enrichment_complete enriched=%d not_found=%d "
                    "calls_used=%d/%d locked=%s",
                    summary["enriched_count"],
                    summary["not_found_count"],
                    summary["calls_used"],
                    summary["call_limit"],
                    summary["locked"],
                )
        except Exception as exc:
            import traceback
            logger.error(
                "realie_enrichment_failed error=%s\n%s", exc, traceback.format_exc()
            )

    asyncio.create_task(_run())

    log_observation(
        logger,
        "realie_enrichment_queued",
        trace_id=trace_id,
        source="realie",
    )
    return {
        "status": "started",
        "trace_id": trace_id,
        "queued_at": format_timestamp(queued_at),
    }
