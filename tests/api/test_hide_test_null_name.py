"""Regression: the ``hide_test`` opportunity filter must be NULL-name-safe.

Every Crexi opportunity has ``name IS NULL``. The original filter used
``~Opportunity.name.ilike('%e2e%')`` which evaluates to NULL (not TRUE) for a
NULL name, so SQL excluded the row — silently hiding the entire Crexi
inventory whenever "Hide Test" was on (the admin default). A NULL name is not
a test fixture and must be kept.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_deals_pipeline import _apply_opp_filters
from app.models.opportunity import Opportunity, OpportunitySource
from tests.conftest import seed_org


async def _opp(session, org, user, *, name, source=OpportunitySource.user_generated.value):
    opp = Opportunity(
        id=uuid.uuid4(),
        org_id=org.id,
        name=name,
        source=source,
        source_id=uuid.uuid4().hex,
        source_url=f"https://example.com/{uuid.uuid4().hex}",
        created_by_user_id=user.id,
    )
    session.add(opp)
    await session.flush()
    return opp


async def test_hide_test_keeps_null_name_and_real_drops_fixtures(session: AsyncSession):
    org, user = await seed_org(session)

    crexi_null = await _opp(session, org, user, name=None, source=OpportunitySource.crexi.value)
    real = await _opp(session, org, user, name="123 Oak Ave — 12 units")
    e2e = await _opp(session, org, user, name="E2E Smoke Deal")
    phase = await _opp(session, org, user, name="Phase 1 Test Deal")
    await session.commit()

    stmt = _apply_opp_filters(select(Opportunity), False, [], None, None, [], True)
    ids = {r.id for r in (await session.execute(stmt)).scalars().unique().all()}

    assert crexi_null.id in ids   # NULL name kept (the bug)
    assert real.id in ids         # real listing kept
    assert e2e.id not in ids      # "e2e" fixture hidden
    assert phase.id not in ids    # "phase N test N" fixture hidden
