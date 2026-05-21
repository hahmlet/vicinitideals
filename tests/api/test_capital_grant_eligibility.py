"""Per-Use eligibility + grant cap (`source.maximum`) API behavior.

Tests the model-builder save handler in app/api/routers/ui.py:
  - `source_maximum` form field persists to source.maximum JSONB
  - `eligible_use_ids[]` form field syncs onto use_lines.eligible_module_ids
  - Validation: maximum requires eligibility; eligibility requires maximum
  - Bidirectional removal: unticking a Use clears the back-reference

Like other tests in tests/api/, these depend on the SQLite/JSONB conftest
helper and may error until that pre-existing infra issue is resolved.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.capital import CapitalModule
from app.models.deal import UseLine


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def test_save_grant_with_eligibility_persists_maximum(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, project, _ = await seed_deal_model_with_financials(session, opp, user)

    # Seed a Use line to point eligibility at
    use_line = UseLine(
        project_id=project.id,
        label="Site Work",
        phase="construction",
        amount=Decimal("180000"),
        cost_category="hard",
    )
    session.add(use_line)
    await session.commit()

    await _auth(client, user.id)
    resp = await client.post(
        f"/ui/forms/{deal_model.id}/capital-modules",
        data=[
            ("label", "OR-MEP"),
            ("vehicle_type", "grant"),
            ("source_maximum", "250000"),
            ("stack_position", "3"),
            ("eligible_use_ids", str(use_line.id)),
            ("ds_active_from_milestone", ""),
            ("ds_active_from_offset_days", "0"),
            ("ds_draw_every_n_months", "1"),
        ],
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    rows = (
        await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == deal_model.id)
        )
    ).scalars().all()
    grant = next((m for m in rows if m.label == "OR-MEP"), None)
    assert grant is not None
    assert Decimal(str(grant.source.get("maximum") or 0)) == Decimal("250000")

    # Use line should now reference the grant in eligible_module_ids
    refreshed_use = await session.get(UseLine, use_line.id)
    assert refreshed_use is not None
    assert any(str(x) == str(grant.id) for x in (refreshed_use.eligible_module_ids or []))


async def test_save_rejects_maximum_without_eligibility(
    client: AsyncClient, session: AsyncSession
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
            "label": "Bad Grant",
            "vehicle_type": "grant",
            "source_maximum": "250000",
            "stack_position": "3",
            "ds_active_from_milestone": "",
            "ds_active_from_offset_days": "0",
            "ds_draw_every_n_months": "1",
        },
    )
    assert resp.status_code == 422


async def test_save_rejects_eligibility_without_maximum(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, project, _ = await seed_deal_model_with_financials(session, opp, user)

    use_line = UseLine(
        project_id=project.id,
        label="Site Work",
        phase="construction",
        amount=Decimal("180000"),
        cost_category="hard",
    )
    session.add(use_line)
    await session.commit()

    await _auth(client, user.id)
    resp = await client.post(
        f"/ui/forms/{deal_model.id}/capital-modules",
        data=[
            ("label", "Bad Grant"),
            ("vehicle_type", "grant"),
            ("stack_position", "3"),
            ("eligible_use_ids", str(use_line.id)),
            ("ds_active_from_milestone", ""),
            ("ds_active_from_offset_days", "0"),
            ("ds_draw_every_n_months", "1"),
        ],
    )
    assert resp.status_code == 422


async def test_clearing_eligibility_removes_back_reference(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, project, _ = await seed_deal_model_with_financials(session, opp, user)

    # Pre-existing grant linked to a Use
    use_line = UseLine(
        project_id=project.id,
        label="Site Work",
        phase="construction",
        amount=Decimal("180000"),
        cost_category="hard",
    )
    session.add(use_line)
    await session.flush()

    grant = CapitalModule(
        scenario_id=deal_model.id,
        label="OR-MEP",
        vehicle_type="grant",
        stack_position=3,
        source={"maximum": 250000.0},
        carry={},
        exit_terms={},
    )
    session.add(grant)
    await session.flush()

    use_line.eligible_module_ids = [grant.id]
    await session.commit()

    await _auth(client, user.id)
    # PUT with no eligible_use_ids AND no maximum (legacy fixed-amount path)
    resp = await client.put(
        f"/ui/forms/{deal_model.id}/capital-modules/{grant.id}",
        data={
            "label": "OR-MEP",
            "vehicle_type": "grant",
            "source_amount": "100000",
            "stack_position": "3",
            "ds_active_from_milestone": "",
            "ds_active_from_offset_days": "0",
            "ds_draw_every_n_months": "1",
        },
    )
    assert resp.status_code in (200, 204), resp.text

    session.expire_all()
    refreshed = await session.get(UseLine, use_line.id)
    assert refreshed is not None
    assert not any(str(x) == str(grant.id) for x in (refreshed.eligible_module_ids or []))
