"""Integration tests for the Gap Adjustment slider endpoint.

Confirms POST /api/models/{model_id}/sliders correctly:
- Upserts the three phantom rows (or leaves them alone when delta=None)
- Persists negative amounts (PP delta and OpEx delta can be negative)
- Returns post-compute metrics
- Reports has_any_adjustment correctly
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import (
    IncomeStream,
    OperatingExpenseLine,
    UseLine,
)
from app.schemas.gap_adjustment_names import (
    OPEX_ADJUSTMENT_LABEL,
    PURCHASE_PRICE_ADJUSTMENT_LABEL,
    REVENUE_ADJUSTMENT_LABEL,
)


async def _seeded_model(session: AsyncSession):
    """Seed a minimal deal model + project + financials.

    Returns ``(model_id, project_id)`` — both are fresh UUIDs per test, but
    since the in-memory engine is shared across the test session, queries in
    assertions must filter by project_id (or model_id) to avoid picking up
    rows from previous tests' commits.
    """
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    from app.models.project import Project as _Project
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    await session.commit()
    project = (await session.execute(
        select(_Project).where(_Project.scenario_id == deal_model.id)
    )).scalar_one()
    return deal_model.id, project.id


@pytest.mark.asyncio
async def test_sliders_upsert_creates_three_phantom_rows(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id = await _seeded_model(session)

    resp = await client.post(
        f"/api/models/{model_id}/sliders",
        json={
            "revenue_delta_monthly": "1000",
            "opex_delta_annual": "-12000",
            "pp_delta": "-50000",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_any_adjustment"] is True
    assert Decimal(body["revenue_delta_monthly"]) == Decimal("1000")
    assert Decimal(body["opex_delta_annual"]) == Decimal("-12000")
    assert Decimal(body["pp_delta"]) == Decimal("-50000")

    # All three phantom rows now exist with the right amounts and labels.
    revenue = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id, IncomeStream.label == REVENUE_ADJUSTMENT_LABEL)
    )).scalar_one()
    assert Decimal(str(revenue.amount_fixed_monthly)) == Decimal("1000")

    opex = (await session.execute(
        select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id, OperatingExpenseLine.label == OPEX_ADJUSTMENT_LABEL)
    )).scalar_one()
    assert Decimal(str(opex.annual_amount)) == Decimal("-12000")

    pp = (await session.execute(
        select(UseLine).where(UseLine.project_id == project_id, UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL)
    )).scalar_one()
    assert Decimal(str(pp.amount)) == Decimal("-50000")


@pytest.mark.asyncio
async def test_sliders_upsert_updates_existing_rows(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Calling the endpoint twice should update, not create duplicates."""
    model_id, project_id = await _seeded_model(session)

    await client.post(
        f"/api/models/{model_id}/sliders",
        json={"revenue_delta_monthly": "500"},
    )
    await client.post(
        f"/api/models/{model_id}/sliders",
        json={"revenue_delta_monthly": "1500"},
    )

    rows = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id, IncomeStream.label == REVENUE_ADJUSTMENT_LABEL)
    )).scalars().all()
    assert len(rows) == 1
    assert Decimal(str(rows[0].amount_fixed_monthly)) == Decimal("1500")


@pytest.mark.asyncio
async def test_sliders_omitted_field_leaves_row_alone(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Sending revenue_delta_monthly=2000 then a request without it must NOT
    reset revenue. The endpoint only touches fields explicitly provided."""
    model_id, project_id = await _seeded_model(session)

    await client.post(
        f"/api/models/{model_id}/sliders",
        json={"revenue_delta_monthly": "2000"},
    )
    # Second request only touches opex; revenue should be untouched.
    resp = await client.post(
        f"/api/models/{model_id}/sliders",
        json={"opex_delta_annual": "-5000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["revenue_delta_monthly"]) == Decimal("2000")
    assert Decimal(body["opex_delta_annual"]) == Decimal("-5000")
    assert Decimal(body["pp_delta"]) == Decimal("0")


@pytest.mark.asyncio
async def test_sliders_zero_delta_keeps_row(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Drag-to-zero stores 0 as the amount; row persists for next session."""
    model_id, project_id = await _seeded_model(session)

    await client.post(
        f"/api/models/{model_id}/sliders",
        json={"revenue_delta_monthly": "1000"},
    )
    await client.post(
        f"/api/models/{model_id}/sliders",
        json={"revenue_delta_monthly": "0"},
    )

    rows = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id, IncomeStream.label == REVENUE_ADJUSTMENT_LABEL)
    )).scalars().all()
    assert len(rows) == 1
    assert Decimal(str(rows[0].amount_fixed_monthly)) == Decimal("0")


@pytest.mark.asyncio
async def test_sliders_has_any_adjustment_false_when_all_zero(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """All three at zero → has_any_adjustment=False. Drives the pill state."""
    model_id, project_id = await _seeded_model(session)

    resp = await client.post(
        f"/api/models/{model_id}/sliders",
        json={
            "revenue_delta_monthly": "0",
            "opex_delta_annual": "0",
            "pp_delta": "0",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["has_any_adjustment"] is False


@pytest.mark.asyncio
async def test_sliders_empty_request_reports_zeros_no_rows_created(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """No deltas at all should still recompute and respond, no phantom rows."""
    model_id, project_id = await _seeded_model(session)

    resp = await client.post(f"/api/models/{model_id}/sliders", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_any_adjustment"] is False
    assert Decimal(body["revenue_delta_monthly"]) == Decimal("0")

    # No phantom rows materialized.
    rows = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id, IncomeStream.label == REVENUE_ADJUSTMENT_LABEL)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_sliders_404_for_unknown_model(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from uuid import uuid4
    resp = await client.post(
        f"/api/models/{uuid4()}/sliders",
        json={"revenue_delta_monthly": "1000"},
    )
    assert resp.status_code == 404
