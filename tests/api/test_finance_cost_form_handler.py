"""Form handler: user edit on auto Total Finance Costs row flips
is_auto_finance_cost to False so the engine stops recomputing it.

Delete + recompute regenerates the row with flag=True (engine writeback path,
not tested here — covered in cashflow integration tests).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.deal import UseLine, UseLinePhase
from app.models.project import Project
from sqlalchemy import select


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def test_user_edit_flips_auto_finance_cost_flag(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    # Seed an engine-managed Total Finance Costs row.
    auto_row = UseLine(
        id=uuid4(),
        project_id=project.id,
        label="Construction Loan — Total Finance Costs",
        phase=UseLinePhase.pre_construction,
        cost_category="soft",
        amount=Decimal("20000"),
        timing_type="first_day",
        is_auto_finance_cost=True,
    )
    session.add(auto_row)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.put(
        f"/ui/forms/{deal_model.id}/use-lines/{auto_row.id}",
        data={
            "label": "Construction Loan — Total Finance Costs",
            "amount": "17500",  # user override
            "cost_category": "soft",
            "timing_type": "first_day",
            "is_deferred": "false",
        },
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(UseLine, auto_row.id)
    assert row is not None
    assert row.is_auto_finance_cost is False, (
        "User edit on an auto finance cost row must flip the flag to False so "
        "the engine stops recomputing it."
    )
    assert Decimal(str(row.amount)) == Decimal("17500")
