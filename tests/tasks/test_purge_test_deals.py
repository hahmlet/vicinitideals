"""Tests for the test-deal janitor (``app.services.test_cleanup.purge_test_deals``).

Covers:
  - a matching deal (Opportunity + top-level Deal + Scenario + Project + financial
    children) is fully purged, top-level Deal row included;
  - a non-matching ("real") deal is never touched;
  - the age guard keeps a freshly-created matching deal (an in-flight test run);
  - dry-run changes nothing;
  - an already-orphaned test ``Deal`` row (its scenario gone) is still swept —
    even when zero opportunities match (the leftover state this task heals).

IDs are captured *before* the purge: ``purge_test_deals`` commits internally,
which expires the ORM instances, so touching their attributes afterwards would
trigger sync IO. ``expunge_all`` clears the identity map so the post-purge
existence checks re-read from the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, Scenario
from app.models.opportunity import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)
from app.services.test_cleanup import purge_test_deals
from tests.conftest import seed_deal_model_with_financials, seed_org


async def _test_opp(
    session: AsyncSession, org, user, *, name: str, age_hours: int
) -> Opportunity:
    """Create an Opportunity with a controlled ``last_seen_at`` (== scraped_at)."""
    opp = Opportunity(
        id=uuid.uuid4(),
        org_id=org.id,
        name=name,
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.user_generated,
        source_url=f"hypothetical://{uuid.uuid4().hex}",
        created_by_user_id=user.id,
        last_seen_at=datetime.now(UTC) - timedelta(hours=age_hours),
    )
    session.add(opp)
    await session.flush()
    return opp


async def test_purges_matching_keeps_real_and_recent(session: AsyncSession):
    org, user = await seed_org(session)

    old = await _test_opp(session, org, user, name="E2E Test Deal A", age_hours=48)
    old_dm, *_ = await seed_deal_model_with_financials(session, old, user)

    recent = await _test_opp(session, org, user, name="E2E Test Deal B", age_hours=1)
    recent_dm, *_ = await seed_deal_model_with_financials(session, recent, user)

    real = await _test_opp(
        session, org, user, name="123 Main Street Acquisition", age_hours=48
    )
    real_dm, *_ = await seed_deal_model_with_financials(session, real, user)
    await session.commit()

    # Capture IDs before purge expires the instances.
    old_id, old_scen, old_deal = old.id, old_dm.id, old_dm.deal_id
    recent_id, recent_deal = recent.id, recent_dm.deal_id
    real_id, real_deal = real.id, real_dm.deal_id

    result = await purge_test_deals(session, execute=True, max_age_hours=24)
    session.expunge_all()

    # Only the old, matching deal is removed — opportunity, scenario AND top deal.
    assert result["matched"]["opportunities"] == 1
    assert result["matched"]["deals"] == 1
    assert await session.get(Opportunity, old_id) is None
    assert await session.get(Scenario, old_scen) is None
    assert await session.get(Deal, old_deal) is None

    # Recent matching deal protected by the age guard; real deal never matched.
    assert await session.get(Opportunity, recent_id) is not None
    assert await session.get(Deal, recent_deal) is not None
    assert await session.get(Opportunity, real_id) is not None
    assert await session.get(Deal, real_deal) is not None


async def test_dry_run_changes_nothing(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await _test_opp(session, org, user, name="E2E Dry Run", age_hours=48)
    dm, *_ = await seed_deal_model_with_financials(session, opp, user)
    await session.commit()
    opp_id, deal_id = opp.id, dm.deal_id

    result = await purge_test_deals(session, execute=False, max_age_hours=None)
    session.expunge_all()

    assert result["executed"] is False
    assert result["matched"]["opportunities"] == 1
    assert await session.get(Opportunity, opp_id) is not None
    assert await session.get(Deal, deal_id) is not None


async def test_purges_diag_harness_deal_keeps_lookalikes(session: AsyncSession):
    """``DIAG <6 hex>`` diagnostic deals are swept; real lookalike names are kept."""
    org, user = await seed_org(session)

    diag = await _test_opp(session, org, user, name="DIAG 0c317c", age_hours=48)
    diag_dm, *_ = await seed_deal_model_with_financials(session, diag, user)

    real1 = await _test_opp(session, org, user, name="Diagnostics Center", age_hours=48)
    real1_dm, *_ = await seed_deal_model_with_financials(session, real1, user)
    real2 = await _test_opp(session, org, user, name="Diagonal Plaza", age_hours=48)
    real2_dm, *_ = await seed_deal_model_with_financials(session, real2, user)

    await session.commit()
    diag_id, diag_deal = diag.id, diag_dm.deal_id
    real1_id, real1_deal = real1.id, real1_dm.deal_id
    real2_id, real2_deal = real2.id, real2_dm.deal_id

    result = await purge_test_deals(session, execute=True, max_age_hours=24)
    session.expunge_all()

    assert result["matched"]["opportunities"] == 1
    assert await session.get(Opportunity, diag_id) is None
    assert await session.get(Deal, diag_deal) is None
    assert await session.get(Opportunity, real1_id) is not None
    assert await session.get(Deal, real1_deal) is not None
    assert await session.get(Opportunity, real2_id) is not None
    assert await session.get(Deal, real2_deal) is not None


async def test_sweeps_orphan_test_deal_with_zero_matching_opps(session: AsyncSession):
    """A test-named Deal whose scenario is already gone still gets swept."""
    org, user = await seed_org(session)
    orphan = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Phase B Test 9 — Orphan",
        created_by_user_id=user.id,
    )
    keep = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Real Orphan Deal",
        created_by_user_id=user.id,
    )
    session.add_all([orphan, keep])
    await session.flush()
    orphan_id, keep_id = orphan.id, keep.id
    await session.commit()

    result = await purge_test_deals(session, execute=True, max_age_hours=None)
    session.expunge_all()

    assert result["matched"]["opportunities"] == 0
    assert result["matched"]["deals"] == 1
    assert result["rows_affected"].get("deals") == 1
    assert await session.get(Deal, orphan_id) is None
    assert await session.get(Deal, keep_id) is not None
