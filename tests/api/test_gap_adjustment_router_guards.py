"""Router-level guards: phantom Gap Adjustment rows can't be deleted or
edited via the public CRUD endpoints.

The slider feature owns the three reserved labels and manages their
lifecycle through the dedicated /sliders endpoint. Direct mutations via
the line-item REST endpoints would break that contract, so each
PATCH/DELETE handler refuses with HTTP 403 when the target row's label
is reserved.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import (
    IncomeStream,
    OperatingExpenseLine,
    UseLine,
    UseLinePhase,
)
from app.models.project import Project
from app.schemas.gap_adjustment_names import (
    OPEX_ADJUSTMENT_LABEL,
    PURCHASE_PRICE_ADJUSTMENT_LABEL,
    REVENUE_ADJUSTMENT_LABEL,
)


async def _seed_phantom_rows(
    session: AsyncSession,
    project_id: UUID,
) -> tuple[UUID, UUID, UUID]:
    """Insert all three phantom rows directly via ORM (bypasses validators).

    Returns (income_stream_id, expense_line_id, use_line_id).
    """
    income = IncomeStream(
        id=uuid4(),
        project_id=project_id,
        stream_type="residential_rent",
        label=REVENUE_ADJUSTMENT_LABEL,
        amount_fixed_monthly=Decimal("1000"),
        active_in_phases=["stabilized", "exit"],
    )
    expense = OperatingExpenseLine(
        id=uuid4(),
        project_id=project_id,
        label=OPEX_ADJUSTMENT_LABEL,
        annual_amount=Decimal("-12000"),
        active_in_phases=["stabilized", "exit"],
    )
    use = UseLine(
        id=uuid4(),
        project_id=project_id,
        label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
        phase=UseLinePhase.acquisition,
        amount=Decimal("-50000"),
    )
    session.add_all([income, expense, use])
    await session.flush()
    return income.id, expense.id, use.id


# ---------------------------------------------------------------------------
# DELETE guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_income_stream_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    income_id, _, _ = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.delete(f"/api/models/{deal_model.id}/income-streams/{income_id}")
    assert resp.status_code == 403, resp.text
    assert "Gap Adjustment phantom row" in resp.text


@pytest.mark.asyncio
async def test_delete_expense_line_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    _, expense_id, _ = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.delete(f"/api/models/{deal_model.id}/expense-lines/{expense_id}")
    assert resp.status_code == 403, resp.text
    assert "Gap Adjustment phantom row" in resp.text


@pytest.mark.asyncio
async def test_delete_use_line_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    _, _, use_id = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.delete(f"/api/models/{deal_model.id}/use-lines/{use_id}")
    assert resp.status_code == 403, resp.text
    assert "Gap Adjustment phantom row" in resp.text


# ---------------------------------------------------------------------------
# PATCH guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_income_stream_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    income_id, _, _ = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.patch(
        f"/api/models/{deal_model.id}/income-streams/{income_id}",
        json={"amount_fixed_monthly": "2000"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_patch_expense_line_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    _, expense_id, _ = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.patch(
        f"/api/models/{deal_model.id}/expense-lines/{expense_id}",
        json={"annual_amount": "-15000"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_patch_use_line_rejects_phantom(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        Project.__table__.select().where(Project.scenario_id == deal_model.id)
    )).first()
    project_id = project.id
    _, _, use_id = await _seed_phantom_rows(session, project_id)
    await session.commit()

    resp = await client.patch(
        f"/api/models/{deal_model.id}/use-lines/{use_id}",
        json={"amount": "-75000"},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Positive control: non-phantom rows still work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_normal_income_stream_still_works(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Sanity: the guard only blocks reserved labels; normal rows pass."""
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, income, _ = await seed_deal_model_with_financials(session, opp, user)
    await session.commit()

    resp = await client.delete(
        f"/api/models/{deal_model.id}/income-streams/{income.id}"
    )
    assert resp.status_code == 204, resp.text
