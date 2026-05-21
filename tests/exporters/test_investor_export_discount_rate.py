"""Discount Rate / Hurdle fallback in investor_export.

When ``scenario.discount_rate_pct`` is NULL the engine context now resolves
the org/user IRR Hurdle Tier 1 default (Bug 2 fix) instead of the hardcoded
per-deal-type table. Per-type table is kept as the last-resort fallback for
scenarios with no creator user / org context.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import (
    _DISCOUNT_RATE_DEFAULTS,
    _resolve_discount_rate_default,
)
from app.models.deal import Deal, ProjectType
from app.models.settings import OrgSetting

from tests.conftest import seed_deal_model, seed_opportunity, seed_org


pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, label: str, project_type: ProjectType):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user, name=label)
    deal_model = await seed_deal_model(
        session, opportunity, user, project_type=project_type
    )
    deal = (
        await session.execute(select(Deal).where(Deal.id == deal_model.deal_id))
    ).scalar_one()
    return org, user, deal_model, deal


async def test_resolve_falls_back_to_per_type_when_no_user(session: AsyncSession):
    _, _, deal_model, deal = await _seed(
        session, "DR-Test-NoUser", ProjectType.value_add
    )
    deal_model.created_by_user_id = None
    await session.flush()

    rate = await _resolve_discount_rate_default(deal_model, deal, session)
    assert rate == _DISCOUNT_RATE_DEFAULTS["value_add"]


async def test_resolve_prefers_org_irr_hurdle_tier1(session: AsyncSession):
    org, _, deal_model, deal = await _seed(
        session, "DR-Test-OrgSet", ProjectType.new_construction
    )

    session.add(OrgSetting(
        org_id=org.id,
        field_key="irr_hurdle_pct_tier1",
        value="9.5",
    ))
    await session.flush()

    rate = await _resolve_discount_rate_default(deal_model, deal, session)
    assert rate == Decimal("9.5")


async def test_resolve_falls_through_to_system_baseline(session: AsyncSession):
    """No org override and no user override → resolver returns SYSTEM_BASELINE
    value for irr_hurdle_pct_tier1 (8.0), not the per-type table."""
    _, _, deal_model, deal = await _seed(
        session, "DR-Test-Baseline", ProjectType.new_construction
    )

    rate = await _resolve_discount_rate_default(deal_model, deal, session)
    assert rate == Decimal("8.0")
