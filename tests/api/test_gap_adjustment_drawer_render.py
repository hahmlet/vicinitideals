"""Integration test for the Gap Adjustment slider drawer rendering.

Confirms that GET /ui/panel/{model_id}?module=sources_uses includes the
drawer markup, slider inputs are pre-filled from existing phantom rows,
and the JS hooks are wired to the /sliders endpoint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import (
    IncomeStream,
    OperatingExpenseLine,
    UseLine,
    UseLinePhase,
)
from app.schemas.gap_adjustment_names import (
    OPEX_ADJUSTMENT_LABEL,
    PURCHASE_PRICE_ADJUSTMENT_LABEL,
    REVENUE_ADJUSTMENT_LABEL,
)


async def _seeded_model(session: AsyncSession, client: AsyncClient):
    """Seed org/user/scenario and authenticate *client* as the seeded user
    (HTMX requests no longer bypass the session gate — 2026-07-08 fix)."""
    from tests.conftest import (
        seed_org, seed_deal_model_with_financials, seed_opportunity, set_client_auth,
    )
    from sqlalchemy import select
    from app.models.project import Project as _Project
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        select(_Project).where(_Project.scenario_id == deal_model.id)
    )).scalar_one()
    await session.commit()
    set_client_auth(client, user.id)
    return deal_model.id, project.id


@pytest.mark.asyncio
async def test_drawer_renders_on_sources_uses_panel(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    model_id, project_id = await _seeded_model(session, client)

    # The drawer only renders when there is a Sources/Uses gap (or a phantom
    # adjustment row already exists), and the gap is only computed once BOTH
    # totals exist — capital_total is None with no funded Sources. Seed a
    # $100k Source (with its per-project junction amount) against a $250k
    # Use so gap = $150k and the drawer shows.
    from uuid import uuid4 as _uuid4
    from app.models.capital import CapitalModule, CapitalModuleProject
    mod = CapitalModule(
        id=_uuid4(),
        scenario_id=model_id,
        label="Equity",
        vehicle_type="equity",
        stack_position=1,
        source={"amount": 100000.0},
        carry={},
        exit_terms={},
    )
    session.add(mod)
    await session.flush()
    session.add_all([
        CapitalModuleProject(
            capital_module_id=mod.id,
            project_id=project_id,
            amount=Decimal("100000"),
        ),
        UseLine(
            project_id=project_id,
            label="Site Work",
            phase=UseLinePhase.construction,
            amount=Decimal("250000"),
            timing_type="first_day",
        ),
    ])
    await session.commit()

    resp = await client.get(
        f"/ui/panel/{model_id}?module=sources_uses",
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200, resp.text
    html = resp.text

    # Drawer container present
    assert 'id="gap-adj-drawer"' in html
    assert "Gap Adjustment" in html
    # All three sliders present
    assert 'id="gap-slider-rev"' in html
    assert 'id="gap-slider-opex"' in html
    assert 'id="gap-slider-pp"' in html
    # JS hooks wired
    assert "window.postGapSliders" in html
    assert "window.resetGapSliders" in html
    assert "/api/models/" in html  # the fetch URL
    assert "/sliders" in html
    # Reset button present
    assert "Reset and Recalc" in html


@pytest.mark.asyncio
async def test_drawer_prefills_from_existing_phantom_rows(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """If phantom rows already exist (prior slider session), sliders must
    initialize to those amounts so the user picks up where they left off."""
    from sqlalchemy import select
    model_id, project_id = await _seeded_model(session, client)

    # Seed phantom rows directly via ORM (bypasses validators).
    session.add_all([
        IncomeStream(
            project_id=project_id,
            stream_type="other",
            label=REVENUE_ADJUSTMENT_LABEL,
            amount_fixed_monthly=Decimal("1500"),
            active_in_phases=["lease_up", "stabilized", "exit"],
        ),
        OperatingExpenseLine(
            project_id=project_id,
            label=OPEX_ADJUSTMENT_LABEL,
            annual_amount=Decimal("-8000"),
            active_in_phases=["lease_up", "stabilized", "exit"],
        ),
        UseLine(
            project_id=project_id,
            label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
            phase=UseLinePhase.acquisition,
            amount=Decimal("-25000"),
            timing_type="first_day",
        ),
    ])
    await session.commit()

    resp = await client.get(
        f"/ui/panel/{model_id}?module=sources_uses",
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    html = resp.text

    # Slider value attributes must reflect the phantom row amounts. The
    # revenue slider is denominated ANNUALLY (monthly phantom amount * 12).
    assert 'id="gap-slider-rev"' in html
    assert 'value="18000"' in html
    assert 'id="gap-slider-opex"' in html
    assert 'value="-8000"' in html
    assert 'id="gap-slider-pp"' in html
    assert 'value="-25000"' in html


@pytest.mark.asyncio
async def test_drawer_omitted_on_other_modules(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """The drawer only renders on sources_uses; opening other modules
    shouldn't show it."""
    model_id, _ = await _seeded_model(session, client)

    for module in ("revenue", "opex", "uses"):
        resp = await client.get(
            f"/ui/panel/{model_id}?module={module}",
            headers={"hx-request": "true"},
        )
        if resp.status_code != 200:
            continue  # some modules may not exist
        assert 'id="gap-adj-drawer"' not in resp.text, f"drawer leaked into {module}"
