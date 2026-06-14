"""Crexi listing-lifecycle auto-archive task tests.

Covers ``app.tasks.scraper._archive_stale_crexi_listings``:
  - stale (not re-seen) and sold/off-market Crexi listings get archived
  - fresh listings, non-Crexi listings, and listings linked to a Deal are kept
  - the whole run no-ops when the scraper itself has gone stale (so a stalled
    scraper can't wrongly archive the entire live inventory)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity, OpportunitySource
from app.tasks.scraper import _archive_stale_crexi_listings
from tests.conftest import seed_deal_model_with_financials, seed_org


@pytest.fixture
def _patch_session_local(session: AsyncSession):
    """Wire the AsyncSessionLocal used inside the task to the test session."""

    @asynccontextmanager
    async def _factory():
        yield session

    with patch("app.tasks.scraper.AsyncSessionLocal", _factory):
        yield


async def _crexi_opp(
    session: AsyncSession,
    org,
    user,
    *,
    days_old: int,
    status: str = "Active",
    source: str = OpportunitySource.crexi.value,
    name: str | None = None,
) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        org_id=org.id,
        name=name,
        source=source,
        source_id=uuid.uuid4().hex,
        source_url=f"https://crexi.com/{uuid.uuid4().hex}",
        status=status,
        archived=False,
        last_seen_at=datetime.now(UTC) - timedelta(days=days_old),
        created_by_user_id=user.id,
    )
    session.add(opp)
    await session.flush()
    return opp


async def test_archives_stale_and_sold_keeps_fresh_linked_and_noncrexi(
    session: AsyncSession, _patch_session_local
):
    org, user = await seed_org(session)

    fresh = await _crexi_opp(session, org, user, days_old=1)            # anchor + keep
    stale = await _crexi_opp(session, org, user, days_old=40)           # archive (stale)
    sold = await _crexi_opp(session, org, user, days_old=1, status="Sold")  # archive (status)
    linked = await _crexi_opp(session, org, user, days_old=40)          # keep (has deal)
    noncrexi = await _crexi_opp(
        session, org, user, days_old=40, source=OpportunitySource.manual.value
    )  # keep (manual)
    await seed_deal_model_with_financials(session, linked, user)
    await session.commit()

    result = await _archive_stale_crexi_listings(dry_run=False)
    assert result["archived"] == 2

    async def _archived(opp_id):
        return (await session.get(Opportunity, opp_id)).archived

    assert await _archived(stale.id) is True
    assert await _archived(sold.id) is True
    assert await _archived(fresh.id) is False
    assert await _archived(linked.id) is False
    assert await _archived(noncrexi.id) is False


async def test_dry_run_changes_nothing(session: AsyncSession, _patch_session_local):
    org, user = await seed_org(session)
    await _crexi_opp(session, org, user, days_old=1)       # fresh anchor
    stale = await _crexi_opp(session, org, user, days_old=40)
    await session.commit()

    result = await _archive_stale_crexi_listings(dry_run=True)
    assert result["dry_run"] is True
    assert result["archived"] == 0
    assert result["scanned"] == 1
    assert (await session.get(Opportunity, stale.id)).archived is False


async def test_skips_when_scraper_stalled(session: AsyncSession, _patch_session_local):
    """All Crexi listings stale (no recent scrape) → protect inventory, archive nothing."""
    org, user = await seed_org(session)
    a = await _crexi_opp(session, org, user, days_old=40)
    b = await _crexi_opp(session, org, user, days_old=55)
    await session.commit()

    result = await _archive_stale_crexi_listings(dry_run=False)
    assert result["skipped_reason"] == "scraper_stale"
    assert result["archived"] == 0
    assert (await session.get(Opportunity, a.id)).archived is False
    assert (await session.get(Opportunity, b.id)).archived is False
