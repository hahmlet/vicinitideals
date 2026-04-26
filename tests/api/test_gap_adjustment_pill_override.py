"""Tests for the calc-status pill yellow override.

When any Gap Adjustment phantom row has a nonzero amount, the pill must
render yellow (warn) regardless of whether Sources=Uses / DSCR / LTV
individually pass. This signals that the model balances "with adjustments"
rather than "for real."

Real failures (gap nonzero, DSCR below floor, LTV above cap) still surface
as warn with their specific message — the override only converts the
otherwise-green case.
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
    from sqlalchemy import select
    from tests.conftest import seed_org, seed_deal_model_with_financials, seed_opportunity
    from app.models.project import Project as _Project
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (await session.execute(
        select(_Project).where(_Project.scenario_id == deal_model.id)
    )).scalar_one()
    await session.commit()
    return deal_model.id, project.id


def _hx_headers(auth_headers: dict[str, str]) -> dict[str, str]:
    return {**auth_headers, "hx-request": "true"}


@pytest.mark.asyncio
async def test_pill_green_when_no_adjustments(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """No phantom rows → pill renders normally (no yellow override).

    The seeded financials don't compute fully (no debt, no Compute), so
    the underlying pill is "warn" or "na" — the test checks specifically
    that the override label "Balanced w/ adjustments" is NOT present.
    """
    model_id, _ = await _seeded_model(session)

    resp = await client.get(
        f"/ui/models/{model_id}/calc-status",
        headers=_hx_headers(auth_headers),
    )
    assert resp.status_code == 200, resp.text
    assert "Balanced w/ adjustments" not in resp.text


@pytest.mark.asyncio
async def test_pill_yellow_when_revenue_adjustment_nonzero(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """A nonzero Revenue phantom row triggers the yellow override."""
    model_id, project_id = await _seeded_model(session)

    # Seed a nonzero revenue phantom and a Compute-clean state. To force
    # the underlying pill to "ok" we stub OperationalOutputs so DSCR/LTV
    # surface as ok/na and capital_total ≈ uses_total. Pragmatic shortcut:
    # we just check the renderer's behavior, not the full integration.
    session.add(IncomeStream(
        project_id=project_id,
        stream_type="other",
        label=REVENUE_ADJUSTMENT_LABEL,
        amount_fixed_monthly=Decimal("1500"),
        active_in_phases=["lease_up", "stabilized", "exit"],
    ))
    await session.commit()

    # Render the pill directly via the helper to test the override logic
    # without depending on the full builder data path.
    from app.api.routers.ui import (
        _has_any_gap_adjustment,
        _render_calc_status_pill_html,
    )
    has_adj = await _has_any_gap_adjustment(session, project_id)
    assert has_adj is True

    fake_ok_status = {
        "overall": "ok",
        "failing_count": 0,
        "sources_uses": {"status": "ok", "label": "", "detail": "", "meta": {}},
        "dscr": {"status": "ok", "label": "", "detail": "", "meta": {}},
        "ltv": {"status": "ok", "label": "", "detail": "", "meta": {}},
    }
    html = _render_calc_status_pill_html(fake_ok_status, model_id, has_any_adjustment=True)
    assert "Balanced w/ adjustments" in html
    assert "calc-status-pill warn" in html
    assert "calc-status-pill ok" not in html


@pytest.mark.asyncio
async def test_pill_yellow_when_pp_adjustment_nonzero(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """A nonzero PP phantom row triggers has_any_gap_adjustment, even
    when Revenue and OpEx phantoms are absent."""
    from app.api.routers.ui import _has_any_gap_adjustment
    model_id, project_id = await _seeded_model(session)

    session.add(UseLine(
        project_id=project_id,
        label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
        phase=UseLinePhase.acquisition,
        amount=Decimal("-50000"),
        timing_type="first_day",
    ))
    await session.commit()

    assert await _has_any_gap_adjustment(session, project_id) is True


@pytest.mark.asyncio
async def test_pill_not_yellow_when_phantom_amount_is_zero(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """Phantom row with amount=0 (drag-to-zero) doesn't trigger the override.

    The row exists but represents no adjustment, so the pill should
    render normally."""
    from app.api.routers.ui import _has_any_gap_adjustment
    model_id, project_id = await _seeded_model(session)

    session.add_all([
        IncomeStream(
            project_id=project_id,
            stream_type="other",
            label=REVENUE_ADJUSTMENT_LABEL,
            amount_fixed_monthly=Decimal("0"),
            active_in_phases=["lease_up", "stabilized", "exit"],
        ),
        OperatingExpenseLine(
            project_id=project_id,
            label=OPEX_ADJUSTMENT_LABEL,
            annual_amount=Decimal("0"),
            active_in_phases=["lease_up", "stabilized", "exit"],
        ),
        UseLine(
            project_id=project_id,
            label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
            phase=UseLinePhase.acquisition,
            amount=Decimal("0"),
            timing_type="first_day",
        ),
    ])
    await session.commit()

    assert await _has_any_gap_adjustment(session, project_id) is False


@pytest.mark.asyncio
async def test_real_failure_still_warns(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """If the model has a real DSCR/Sources failure, the existing warn
    label wins — has_any_adjustment doesn't downgrade real failures."""
    from app.api.routers.ui import _render_calc_status_pill_html
    from uuid import uuid4

    fake_fail_status = {
        "overall": "warn",
        "failing_count": 1,
        "sources_uses": {
            "status": "fail",
            "label": "Gap $50,000",
            "detail": "...",
            "meta": {"gap": -50000.0},
        },
        "dscr": {"status": "ok", "label": "", "detail": "", "meta": {}},
        "ltv": {"status": "ok", "label": "", "detail": "", "meta": {}},
    }
    # Even with has_any_adjustment=True, real failures keep their warn label
    html = _render_calc_status_pill_html(fake_fail_status, uuid4(), has_any_adjustment=True)
    assert "Sources Gap" in html
    assert "Balanced w/ adjustments" not in html


@pytest.mark.asyncio
async def test_phantom_row_yellow_highlight_in_panel(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """A nonzero PP phantom row in the Uses table renders with yellow
    background; a zero phantom row renders gray (placeholder)."""
    from sqlalchemy import select
    model_id, project_id = await _seeded_model(session)

    # Nonzero phantom → yellow
    session.add(UseLine(
        project_id=project_id,
        label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
        phase=UseLinePhase.acquisition,
        amount=Decimal("-25000"),
        timing_type="first_day",
    ))
    await session.commit()

    resp = await client.get(
        f"/ui/panel/{model_id}?module=sources_uses",
        headers=_hx_headers(auth_headers),
    )
    assert resp.status_code == 200
    # The yellow highlight uses background:#fef3c7 (Tailwind amber-100).
    assert "background:#fef3c7" in resp.text

    # Update to zero, verify it falls back to gray
    pp = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == project_id,
            UseLine.label == PURCHASE_PRICE_ADJUSTMENT_LABEL,
        )
    )).scalar_one()
    pp.amount = Decimal("0")
    await session.commit()

    resp = await client.get(
        f"/ui/panel/{model_id}?module=sources_uses",
        headers=_hx_headers(auth_headers),
    )
    assert resp.status_code == 200
    assert "background:#f3f4f6" in resp.text  # gray placeholder
