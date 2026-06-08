"""Tests for the deals-list "Gap Adj" column.

Covers ``_gap_adj_by_scenario`` (the batched live Sources/Uses gap +
adjustment-flag computation) and the rendered column on GET /deals.

Gap = Σ committed source principal − Σ UseLine.amount (excl exit phase, incl
the negative Purchase-Price gap-adjustment phantom); signed so a funding
shortfall is negative. ``has_adj`` is True when any Gap Adjustment phantom row
carries a nonzero amount. Cell colors: red = gap, no adjustments; amber =
adjustments applied; green = fully funded, no adjustments.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui import _gap_adj_by_scenario
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import UseLine, UseLinePhase
from app.models.project import Project
from app.schemas.gap_adjustment_names import PURCHASE_PRICE_ADJUSTMENT_LABEL


async def _seed_scenario_with_uses_and_sources(session: AsyncSession):
    """Seed a deal model + project with $1M acq uses, a $0.5M exit line, and
    a $600k source. Returns ``(scenario_id, project_id, user)``."""
    from tests.conftest import (
        seed_deal_model_with_financials,
        seed_opportunity,
        seed_org,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    session.add_all(
        [
            UseLine(
                project_id=project.id,
                label="Acquisition Price",
                phase=UseLinePhase.acquisition.value,
                amount=Decimal("1000000"),
            ),
            # Exit-phase line must NOT count toward the gap.
            UseLine(
                project_id=project.id,
                label="Disposition Cost",
                phase=UseLinePhase.exit.value,
                amount=Decimal("500000"),
            ),
        ]
    )
    module = CapitalModule(
        scenario_id=deal_model.id,
        label="Senior Debt",
        vehicle_type="debt",
        stack_position=0,
    )
    session.add(module)
    await session.flush()
    session.add(
        CapitalModuleProject(
            capital_module_id=module.id,
            project_id=project.id,
            amount=Decimal("600000"),
        )
    )
    await session.commit()
    return deal_model.id, project.id, user


@pytest.mark.asyncio
async def test_gap_adj_base_gap_no_adjustment(session: AsyncSession) -> None:
    scenario_id, _, _ = await _seed_scenario_with_uses_and_sources(session)

    result = await _gap_adj_by_scenario(session, [scenario_id])

    info = result[scenario_id]
    # 600,000 sources − 1,000,000 uses (exit-phase 500k excluded) = -400,000
    # (signed; a funding shortfall reads as a negative number).
    assert info["gap"] == pytest.approx(-400000.0)
    assert info["has_adj"] is False


@pytest.mark.asyncio
async def test_gap_adj_with_purchase_price_phantom(session: AsyncSession) -> None:
    scenario_id, project_id, _ = await _seed_scenario_with_uses_and_sources(session)

    # Apply a -$100k Purchase-Price gap-adjustment phantom.
    session.add(
        UseLine(
            project_id=project_id,
            label=PURCHASE_PRICE_ADJUSTMENT_LABEL,
            phase=UseLinePhase.acquisition.value,
            amount=Decimal("-100000"),
        )
    )
    await session.commit()

    result = await _gap_adj_by_scenario(session, [scenario_id])

    info = result[scenario_id]
    # Uses fall to 900,000; gap = 600,000 − 900,000 = -300,000.
    assert info["gap"] == pytest.approx(-300000.0)
    # A nonzero phantom flips the flag → yellow in the UI.
    assert info["has_adj"] is True


@pytest.mark.asyncio
async def test_gap_adj_empty_scenario_list_returns_empty(session: AsyncSession) -> None:
    assert await _gap_adj_by_scenario(session, []) == {}


def _row(**overrides) -> dict:
    base = {
        "id": "deal-1",
        "name": "Test Deal",
        "address": None,
        "status_badge": "badge-gray",
        "status_display": "Active",
        "type_display": "—",
        "building_description": None,
        "primary_model_name": None,
        "primary_model_id": None,
        "noi": None,
        "irr": None,
        "equity_multiple": None,
        "gap_adj": None,
        "gap_has_adj": False,
        "last_updated_fmt": None,
    }
    base.update(overrides)
    return base


def test_deals_rows_partial_colors_gap_adj_three_states() -> None:
    """Cell color: green (funded, no adj), red (gap, no adj), amber (adjusted);
    shortfalls render as negative dollars."""
    from app.api.routers.ui import templates

    tmpl = templates.env.get_template("partials/deals_rows.html")

    # Fully funded, no adjustments → green, shown as $0.
    green = tmpl.render(deals=[_row(gap_adj=0.0, gap_has_adj=False)])
    assert "$0" in green
    assert "#16a34a" in green  # green
    assert "#dc2626" not in green and "#d97706" not in green

    # Gap with no adjustments → red, shown as a negative number.
    red = tmpl.render(deals=[_row(gap_adj=-400000.0, gap_has_adj=False)])
    assert "-$400,000" in red
    assert "#dc2626" in red  # red
    assert "#d97706" not in red

    # Adjustments applied (gap remains) → amber, even when negative.
    amber = tmpl.render(deals=[_row(gap_adj=-300000.0, gap_has_adj=True)])
    assert "-$300,000" in amber
    assert "#d97706" in amber  # amber
    assert "#dc2626" not in amber

    # Adjustments applied but gap fully closed ($0) → still amber.
    amber_zero = tmpl.render(deals=[_row(gap_adj=0.0, gap_has_adj=True)])
    assert "#d97706" in amber_zero
    assert "#16a34a" not in amber_zero

    # No scenario / no data → muted dash, no color.
    none = tmpl.render(deals=[_row(gap_adj=None)])
    assert "—" in none
    assert "#16a34a" not in none
    assert "#d97706" not in none
    assert "#dc2626" not in none
