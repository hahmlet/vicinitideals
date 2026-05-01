"""Async investor-export Celery task tests.

Exercises the engine + email orchestration without spinning up Celery —
calls the underlying coroutines directly. Patches the Resend HTTP send
so the test passes regardless of ``RESEND_API_KEY`` config.

Lifecycle covered:
  - status starts as ``queued`` and lands at ``sent`` on success
  - ``xlsx_bytes`` + ``filename`` persisted onto the row
  - resend path uses cached bytes (engine is not re-run)
  - email-send failure transitions to ``failed`` with error_message
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_job import ExportJob, ExportJobStatus
from app.tasks.export import (
    _resend_investor_export_async,
    _run_investor_export_async,
)
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


@pytest.fixture
def _patch_session_local(session: AsyncSession):
    """Wire the AsyncSessionLocal used inside the task to the test session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield session

    with patch("app.tasks.export.AsyncSessionLocal", _factory):
        yield


async def _seed_minimal(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Async Export Smoke")
    deal_model, *_ = await seed_deal_model_with_financials(session, opp, user)
    return user, deal_model


async def test_run_investor_export_happy_path(
    session: AsyncSession, _patch_session_local
):
    user, deal_model = await _seed_minimal(session)

    job = ExportJob(
        scenario_id=deal_model.id,
        user_id=user.id,
        recipient_email="lp@example.com",
        status=ExportJobStatus.queued,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    with patch(
        "app.tasks.export.send_export_ready_email",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        result = await _run_investor_export_async(str(job.id))

    assert result == "sent"
    refreshed = await session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.sent
    assert refreshed.xlsx_bytes is not None and len(refreshed.xlsx_bytes) > 0
    assert refreshed.filename and refreshed.filename.endswith(".xlsx")
    assert refreshed.error_message is None
    assert refreshed.completed_at is not None

    # send_export_ready_email called with the persisted bytes/filename.
    mock_send.assert_awaited_once()
    kwargs = mock_send.await_args.kwargs
    assert kwargs["to"] == "lp@example.com"
    assert kwargs["xlsx_bytes"] == refreshed.xlsx_bytes
    assert kwargs["filename"] == refreshed.filename


async def test_run_investor_export_email_failure_marks_failed(
    session: AsyncSession, _patch_session_local
):
    user, deal_model = await _seed_minimal(session)

    job = ExportJob(
        scenario_id=deal_model.id,
        user_id=user.id,
        recipient_email="lp@example.com",
        status=ExportJobStatus.queued,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    with patch(
        "app.tasks.export.send_export_ready_email",
        new=AsyncMock(return_value=False),
    ):
        result = await _run_investor_export_async(str(job.id))

    assert result == "failed"
    refreshed = await session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.failed
    assert refreshed.error_message and "Resend" in refreshed.error_message
    # Bytes still persisted from the calculating step — the resend path
    # uses them when the user retries.
    assert refreshed.xlsx_bytes is not None and len(refreshed.xlsx_bytes) > 0


async def test_resend_uses_cached_bytes_without_rebuild(
    session: AsyncSession, _patch_session_local
):
    """Resend path should never call compute / build — only send the email."""
    user, deal_model = await _seed_minimal(session)

    cached_bytes = b"PK\x03\x04 fake-xlsx-payload"
    job = ExportJob(
        scenario_id=deal_model.id,
        user_id=user.id,
        recipient_email="lp@example.com",
        status=ExportJobStatus.queued,
        xlsx_bytes=cached_bytes,
        filename="cached.xlsx",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    with (
        patch(
            "app.tasks.export.export_investor_workbook",
            new=AsyncMock(side_effect=AssertionError("must not rebuild on resend")),
        ),
        patch(
            "app.tasks.export.send_export_ready_email",
            new=AsyncMock(return_value=True),
        ) as mock_send,
    ):
        result = await _resend_investor_export_async(str(job.id))

    assert result == "sent"
    refreshed = await session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.sent
    assert refreshed.xlsx_bytes == cached_bytes  # untouched

    kwargs = mock_send.await_args.kwargs
    assert kwargs["xlsx_bytes"] == cached_bytes
    assert kwargs["filename"] == "cached.xlsx"


async def test_resend_with_no_cached_bytes_marks_failed(
    session: AsyncSession, _patch_session_local
):
    user, deal_model = await _seed_minimal(session)

    job = ExportJob(
        scenario_id=deal_model.id,
        user_id=user.id,
        recipient_email="lp@example.com",
        status=ExportJobStatus.sent,
        xlsx_bytes=None,
        filename="never-rendered.xlsx",
        completed_at=datetime.now(UTC),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    result = await _resend_investor_export_async(str(job.id))
    assert result == "failed"

    refreshed = await session.get(ExportJob, job.id)
    assert refreshed.status == ExportJobStatus.failed
    assert refreshed.error_message and "no cached" in refreshed.error_message.lower()


async def test_run_investor_export_missing_job_returns_missing(
    session: AsyncSession, _patch_session_local
):
    bogus_id = str(uuid.uuid4())
    result = await _run_investor_export_async(bogus_id)
    assert result == "missing"
