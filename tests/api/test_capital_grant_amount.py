"""Grant / forgivable_loan / tax_credit sources need a user-supplied
source_amount. The model builder form posts source_amount; the handler
must persist it into CapitalModule.source["amount"].

Regression: form had no Amount input for these "simple" source types,
so users could create a Grant with $0 commitment.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.capital import CapitalModule


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


@pytest.mark.parametrize("vehicle_type", ["grant", "forgivable_loan", "tax_credit"])
async def test_create_fixed_amount_source_persists_source_amount(
    client: AsyncClient, session: AsyncSession, vehicle_type: str
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    await _auth(client, user.id)

    resp = await client.post(
        f"/ui/forms/{deal_model.id}/capital-modules",
        data={
            "label": "Test Grant",
            "vehicle_type": vehicle_type,
            "source_amount": "250000",
            "stack_position": "3",
            "ds_active_from_milestone": "",
            "ds_active_from_offset_days": "0",
            "ds_draw_every_n_months": "1",
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    rows = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == deal_model.id)
        )
    ).scalars().all()
    new_mod = next((m for m in rows if m.label == "Test Grant"), None)
    assert new_mod is not None, "Capital module was not created"
    assert new_mod.source is not None
    assert Decimal(str(new_mod.source.get("amount") or 0)) == Decimal("250000")


async def test_edit_grant_source_amount_updates_value(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    existing = CapitalModule(
        scenario_id=deal_model.id,
        label="OR-MEP",
        vehicle_type="grant",
        stack_position=3,
        source={"amount": 100000.0},
        carry={},
        exit_terms={},
    )
    session.add(existing)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{existing.id}",
        data={
            "label": "OR-MEP",
            "vehicle_type": "grant",
            "source_amount": "175000",
            "stack_position": "3",
            "ds_active_from_milestone": "",
            "ds_active_from_offset_days": "0",
            "ds_draw_every_n_months": "1",
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    row = await session.get(CapitalModule, existing.id)
    assert row is not None
    assert Decimal(str(row.source.get("amount") or 0)) == Decimal("175000")
