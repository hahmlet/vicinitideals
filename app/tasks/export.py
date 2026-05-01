"""Celery task that builds an investor Excel export off the request path.

The synchronous endpoint (``GET /ui/models/{id}/investor-export.xlsx``)
hits the NGINX 60s proxy timeout on production multi-project deals once
the live Sensitivity matrix is computed (25 cashflow cycles). This task
runs the same export inside the ``analysis`` queue worker (no proxy in
the way), persists the rendered bytes onto an ``ExportJob`` row so a
"resend last export" click ships the same file without re-running the
engine, and emails the workbook as a Resend attachment when the build
finishes.

Status lifecycle on the ``ExportJob`` row::

    queued → calculating → sending → sent
                              └────→ failed (terminal, with error_message)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.emails.sender import send_export_ready_email
from app.exporters.investor_export import (
    export_investor_workbook,
    make_investor_filename,
)
from app.models.deal import Deal, DealModel
from app.models.export_job import ExportJob, ExportJobStatus
from app.models.org import User
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

RUN_EXPORT_TASK = "app.tasks.export.run_investor_export"
RESEND_EXPORT_TASK = "app.tasks.export.resend_investor_export"


@celery_app.task(bind=True, name=RUN_EXPORT_TASK)
def run_investor_export(self, job_id: str) -> str:
    """Build the workbook, persist bytes, send the email."""
    del self
    return asyncio.run(_run_investor_export_async(job_id))


@celery_app.task(bind=True, name=RESEND_EXPORT_TASK)
def resend_investor_export(self, job_id: str) -> str:
    """Resend a previously-built export from the cached ``xlsx_bytes``."""
    del self
    return asyncio.run(_resend_investor_export_async(job_id))


async def _run_investor_export_async(job_id: str) -> str:
    job_uuid = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job = await session.get(ExportJob, job_uuid)
        if job is None:
            logger.warning("ExportJob %s vanished before worker picked it up", job_id)
            return "missing"

        scenario_id = job.scenario_id

        # Move to "calculating" so the UI status modal updates.
        job.status = ExportJobStatus.calculating
        await session.commit()

        try:
            xlsx_bytes = await export_investor_workbook(scenario_id, session)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Investor export build failed for scenario %s", scenario_id)
            await _mark_failed(session, job_uuid, f"build error: {exc}")
            return "failed"

        scenario = await session.get(DealModel, scenario_id)
        deal = (
            await session.get(Deal, scenario.deal_id) if scenario and scenario.deal_id else None
        )
        filename = make_investor_filename(scenario, deal) if scenario else "investor-export.xlsx"

        # Persist bytes + flip status to "sending" before email out.
        job.xlsx_bytes = xlsx_bytes
        job.filename = filename
        job.status = ExportJobStatus.sending
        await session.commit()

        ok = await _send_export(session, job_uuid)
        if not ok:
            return "failed"
        return "sent"


async def _resend_investor_export_async(job_id: str) -> str:
    job_uuid = UUID(job_id)
    async with AsyncSessionLocal() as session:
        job = await session.get(ExportJob, job_uuid)
        if job is None or not job.xlsx_bytes:
            logger.warning("Resend requested but ExportJob %s has no cached bytes", job_id)
            await _mark_failed(session, job_uuid, "no cached export bytes to resend")
            return "failed"
        job.status = ExportJobStatus.sending
        await session.commit()

        ok = await _send_export(session, job_uuid)
        if not ok:
            return "failed"
        return "sent"


async def _send_export(session, job_uuid: UUID) -> bool:
    job = await session.get(ExportJob, job_uuid)
    if job is None:
        return False
    user = await session.get(User, job.user_id)
    scenario = await session.get(DealModel, job.scenario_id)
    deal = (
        await session.get(Deal, scenario.deal_id) if scenario and scenario.deal_id else None
    )

    try:
        ok = await send_export_ready_email(
            to=job.recipient_email,
            name=(user.name if user else "") or "",
            deal_name=(deal.name if deal else None) or "your deal",
            scenario_name=(scenario.name if scenario else None),
            filename=job.filename or "investor-export.xlsx",
            xlsx_bytes=job.xlsx_bytes or b"",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resend send failed for job %s", job_uuid)
        await _mark_failed(session, job_uuid, f"email error: {exc}")
        return False

    if not ok:
        await _mark_failed(
            session,
            job_uuid,
            "Resend API rejected the message (see api logs)",
        )
        return False

    job = await session.get(ExportJob, job_uuid)
    if job is not None:
        job.status = ExportJobStatus.sent
        job.completed_at = datetime.now(UTC)
        await session.commit()
    return True


async def _mark_failed(session, job_uuid: UUID, message: str) -> None:
    job = await session.get(ExportJob, job_uuid)
    if job is None:
        return
    job.status = ExportJobStatus.failed
    job.error_message = message[:2000]
    job.completed_at = datetime.now(UTC)
    await session.commit()


# Helper for ad-hoc admin lookups during incident response.
async def _summarize_recent_jobs(scenario_id: UUID, limit: int = 10) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(ExportJob)
                .where(ExportJob.scenario_id == scenario_id)
                .order_by(ExportJob.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "status": r.status.value,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "error": r.error_message,
            }
            for r in rows
        ]
