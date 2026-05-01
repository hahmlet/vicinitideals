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


async def _seeded_model(session: AsyncSession):
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    from sqlalchemy import select
    from app.models.project import Project as _Project
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        select(_Project).where(_Project.scenario_id == deal_model.id)
    )).scalar_one()
    await session.commit()
    return deal_model.id, project.id


@pytest.mark.asyncio
async def test_drawer_renders_on_sources_uses_panel(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    model_id, _ = await _seeded_model(session)

    resp = await client.get(
        f"/ui/panel/{model_id}?module=sources_uses",
        headers={**auth_headers, "hx-request": "true"},
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
    assert "Reset all" in html


@pytest.mark.asyncio
async def test_drawer_prefills_from_existing_phantom_rows(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """If phantom rows already exist (prior slider session), sliders must
    initialize to those amounts so the user picks up where they left off."""
    from sqlalchemy import select
    model_id, project_id = await _seeded_model(session)

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
        headers={**auth_headers, "hx-request": "true"},
    )
    assert resp.status_code == 200
    html = resp.text

    # Slider value attributes must reflect the phantom row amounts.
    assert 'id="gap-slider-rev"' in html
    assert 'value="1500"' in html
    assert 'id="gap-slider-opex"' in html
    assert 'value="-8000"' in html
    assert 'id="gap-slider-pp"' in html
    assert 'value="-25000"' in html


@pytest.mark.asyncio
async def test_drawer_omitted_on_other_modules(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """The drawer only renders on sources_uses; opening other modules
    shouldn't show it."""
    model_id, _ = await _seeded_model(session)

    for module in ("revenue", "opex", "uses"):
        resp = await client.get(
            f"/ui/panel/{model_id}?module={module}",
            headers={**auth_headers, "hx-request": "true"},
        )
        if resp.status_code != 200:
            continue  # some modules may not exist
        assert 'id="gap-adj-drawer"' not in resp.text, f"drawer leaked into {module}"
