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
    from tests.conftest import set_client_auth
    set_client_auth(client, user_id)


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


# ---------------------------------------------------------------------------
# Eligibility checklist must hide Gap Adjustment phantom rows and $0 Uses.
# Engine-managed Gap Adjustment Uses cannot be funded by user-chosen grants;
# $0 rows aren't actionable funding targets either.
# ---------------------------------------------------------------------------


async def test_line_form_eligibility_uses_excludes_gap_adjustment_and_zero(
    client: AsyncClient, session: AsyncSession
) -> None:
    from tests.conftest import (
        seed_org, seed_opportunity, seed_deal_model_with_financials,
    )
    from app.schemas.gap_adjustment_names import (
        REVENUE_ADJUSTMENT_LABEL,
        OPEX_ADJUSTMENT_LABEL,
        PURCHASE_PRICE_ADJUSTMENT_LABEL,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, project, _ = await seed_deal_model_with_financials(session, opp, user)

    real_use = UseLine(
        project_id=project.id, label="Site Work", phase="construction",
        amount=Decimal("180000"), cost_category="hard",
    )
    zero_use = UseLine(
        project_id=project.id, label="Reserved Bucket", phase="construction",
        amount=Decimal("0"), cost_category="soft",
    )
    gap_rev = UseLine(
        project_id=project.id, label=REVENUE_ADJUSTMENT_LABEL, phase="construction",
        amount=Decimal("50000"), cost_category="soft",
    )
    gap_opex = UseLine(
        project_id=project.id, label=OPEX_ADJUSTMENT_LABEL, phase="construction",
        amount=Decimal("50000"), cost_category="soft",
    )
    gap_pp = UseLine(
        project_id=project.id, label=PURCHASE_PRICE_ADJUSTMENT_LABEL, phase="acquisition",
        amount=Decimal("50000"), cost_category="hard",
    )
    session.add_all([real_use, zero_use, gap_rev, gap_opex, gap_pp])
    await session.commit()

    await _auth(client, user.id)
    resp = await client.get(
        f"/ui/models/{deal_model.id}/line-form",
        params={"type": "capital_modules"},
    )
    assert resp.status_code == 200
    html = resp.text

    # Real Use shows; phantom + $0 Uses are filtered
    assert "Site Work" in html
    assert "Reserved Bucket" not in html
    assert REVENUE_ADJUSTMENT_LABEL not in html
    assert OPEX_ADJUSTMENT_LABEL not in html
    assert PURCHASE_PRICE_ADJUSTMENT_LABEL not in html
