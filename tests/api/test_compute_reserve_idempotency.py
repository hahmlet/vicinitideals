"""Regression: the compute endpoint must reset its auto-managed Cash Flow
Support Reserve each run so repeated clicks are idempotent.

Production bug: the engine grows a "Cash Flow Support Reserve" use line to
cover an operating shortfall and folds it into total_uses (so the loan grows
to cover it). The reserve was *persisted* and *accumulated* across compute
calls, so every user click stacked onto the prior amount. For
capitalized-interest construction deals that feedback diverged geometrically
(reserve → bigger loan → more debt service → bigger shortfall → bigger
reserve), eventually producing a ~1.3-trillion-% IRR that overflowed the
party_irr_pct NUMERIC(18, 6) column and 500'd the whole compute.

Fix: the endpoint zeroes any persisted reserve before its fix-point loop, then
re-derives it from scratch — converging to the same fixed point regardless of
click history. A divergence guard stops the loop if the shortfall ever stops
shrinking (structural insolvency) instead of looping toward a blow-up.

Run:
    uv run pytest tests/api/test_compute_reserve_idempotency.py -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.deal import UseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = pytest.mark.asyncio

_CFSR = "Cash Flow Support Reserve"


async def _seed_construction_deal(session: AsyncSession) -> tuple[str, str]:
    """A capitalized-interest construction deal whose perm loan auto-sizes —
    the configuration that produced the runaway reserve in production."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    inputs.purchase_price = Decimal("1000000")
    inputs.closing_costs_pct = Decimal("2.0")
    inputs.renovation_cost_total = Decimal("3000000")
    inputs.renovation_months = 12
    inputs.lease_up_months = 6
    inputs.initial_occupancy_pct = Decimal("0")
    session.add(inputs)

    session.add_all(
        [
            UseLine(
                project_id=project.id,
                label="Acquisition",
                phase="acquisition",
                amount=Decimal("1000000"),
                cost_category="hard",
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Hard Costs",
                phase="construction",
                amount=Decimal("3000000"),
                cost_category="hard",
                timing_type="first_day",
            ),
            CapitalModule(
                scenario_id=deal_model.id,
                label="Permanent Loan",
                vehicle_type="debt",
                stack_position=1,
                source={
                    "amount": 0,
                    "interest_rate_pct": 6.5,
                    "auto_size": True,
                    "amort_term_years": 30,
                },
                carry={
                    "carry_type": "capitalized_interest",
                    "payment_frequency": "monthly",
                },
                exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
                active_phase_start="acquisition",
                active_phase_end="exit",
            ),
        ]
    )
    await session.commit()
    return str(deal_model.id), str(project.id)


async def _cfsr_amount(session: AsyncSession, project_id: str) -> Decimal:
    session.expire_all()
    row = (
        await session.execute(
            select(UseLine).where(
                UseLine.project_id == project_id,
                UseLine.label == _CFSR,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return Decimal("0")
    return Decimal(str(row.amount or 0))


async def test_compute_resets_stale_reserve_and_is_idempotent(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    model_id, project_id = await _seed_construction_deal(session)

    # Simulate a runaway reserve accumulated by prior compute clicks: a $5M
    # Cash Flow Support Reserve persisted on the deal. A correct compute must
    # reset this to a fresh fixed point, not stack onto it.
    session.add(
        UseLine(
            project_id=project_id,
            label=_CFSR,
            phase="operation",
            amount=Decimal("5000000"),
            cost_category="soft",
            timing_type="first_day",
        )
    )
    await session.commit()

    # First compute: must NOT 500 (the overflow bug) and must clear the stale
    # reserve rather than fold the $5M into the loan and diverge.
    r1 = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
    assert r1.status_code == 200, r1.text
    cfsr_1 = await _cfsr_amount(session, project_id)
    assert cfsr_1 < Decimal("5000000"), (
        f"stale reserve survived compute: {cfsr_1} — reset did not run"
    )

    # Second compute: idempotent — converges to the SAME reserve, not a larger
    # one. Without the per-run reset this would grow on every click.
    r2 = await client.post(f"/api/models/{model_id}/compute", headers=auth_headers)
    assert r2.status_code == 200, r2.text
    cfsr_2 = await _cfsr_amount(session, project_id)
    assert cfsr_2 == cfsr_1, f"compute not idempotent: {cfsr_1} -> {cfsr_2}"
