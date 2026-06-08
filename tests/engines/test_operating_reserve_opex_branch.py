"""Operating Reserve sizing — opex-heavy branch (Sources = Uses invariant).

The cashflow auto-sizer funds the Operating Reserve on
``max(opex_monthly, ds_monthly) * reserve_months`` (revenue/opex mode,
``ds`` basis). The gap-fill solve already does this via its
``ds_check < opex_monthly_pre`` opex fallback, but the reserve *write-back*
historically booked pure debt-service for the ``ds`` basis.

When monthly opex exceeds monthly debt service (low-leverage /
high-opex deals), the loan was sized to fund the larger opex-based
reserve while the model only *booked* the smaller DS-based reserve —
leaving the difference as a phantom Sources/Uses **surplus**
(regression: Hazelwood Commons, scenario 4a4e70cf, ~$79k surplus).

The ds-heavy direction is covered by
``tests/exporters/test_sources_uses_operating_reserve_parity.py``.
This test covers the opposite (opex-heavy) branch.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import _monthly_pmt, compute_cash_flows
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    EquityRole,
    VehicleType,
)
from app.models.deal import UseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = pytest.mark.asyncio


async def _seed_opex_heavy_scenario(session: AsyncSession):
    """Seed a stack whose monthly opex clearly exceeds monthly debt service.

    Modest acquisition + low equity → a small auto-sized loan (low DS),
    paired with a large operating expense → the engine's
    ``max(opex, ds)`` reserve lands on the *opex* branch.
    """
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="OpReserve OpEx Branch")
    deal_model, inputs, seeded_stream, seeded_opex = (
        await seed_deal_model_with_financials(session, opp, user)
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    # Reserve sized on debt service (the default, and the branch with the bug).
    inputs.operation_reserve_basis = "ds"
    inputs.operation_reserve_months = 6

    seeded_stream.active_in_phases = ["stabilized"]
    # Large opex so opex_monthly >> ds_monthly on a small loan.
    seeded_opex.active_in_phases = ["stabilized"]
    seeded_opex.annual_amount = Decimal("900000")  # $75k/mo

    debt = CapitalModule(
        scenario_id=deal_model.id,
        label="Senior PI Loan",
        vehicle_type=VehicleType.debt.value,
        stack_position=1,
        source={
            "amount": "2000000",
            "interest_rate_pct": 6.0,
            "amort_term_years": 30,
            "hold_term_years": 30,
            "auto_size": True,
            "binding_constraint": "gap_fill",
        },
        carry={
            "phases": [
                {"name": "construction", "carry_type": "pi"},
                {"name": "operation", "carry_type": "pi"},
            ]
        },
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(debt)

    session.add(
        UseLine(
            project_id=project.id,
            label="Land Acquisition",
            amount=Decimal("2000000"),
            phase="acquisition",
            cost_category="hard",
        )
    )
    await session.flush()

    session.add(
        CapitalModuleProject(
            capital_module_id=debt.id,
            project_id=project.id,
            amount=Decimal("2000000"),
        )
    )
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model, project


async def _project_totals(session: AsyncSession, project_id):
    uses = (
        await session.execute(
            select(UseLine).where(UseLine.project_id == project_id)
        )
    ).scalars().all()
    uses_total = sum(
        (Decimal(str(u.amount)) for u in uses if (u.phase or "") != "exit"),
        Decimal("0"),
    )
    src_rows = (
        await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.project_id == project_id
            )
        )
    ).scalars().all()
    sources_total = sum(
        (Decimal(str(s.amount)) for s in src_rows), Decimal("0")
    )
    op_reserve = next((u for u in uses if u.label == "Operating Reserve"), None)
    return uses_total, sources_total, op_reserve


async def test_opex_heavy_no_sources_uses_surplus(
    session: AsyncSession,
) -> None:
    """Loan funds an opex-based reserve, so Uses must equal Sources.

    Before the fix the reserve was booked debt-service-based while the
    loan was sized opex-based → Sources exceeded Uses by the gap.
    """
    _scenario, project = await _seed_opex_heavy_scenario(session)
    uses_total, sources_total, op_reserve = await _project_totals(
        session, project.id
    )

    assert op_reserve is not None, "fixture should book an Operating Reserve"
    # Sources = Uses within whole-dollar loan rounding.
    diff = abs(sources_total - uses_total)
    assert diff < Decimal("2"), (
        f"Sources/Uses surplus regression: sources={sources_total}, "
        f"uses={uses_total}, diff={diff}. The loan funds max(opex, ds) but "
        f"the reserve was booked on debt service only."
    )


async def test_opex_heavy_reserve_is_opex_driven(
    session: AsyncSession,
) -> None:
    """Operating Reserve must exceed the pure debt-service reserve.

    Proves the ``max(opex, ds)`` write-back selected the opex branch
    rather than booking debt service alone.
    """
    _scenario, project = await _seed_opex_heavy_scenario(session)
    _uses, _sources, op_reserve = await _project_totals(session, project.id)
    assert op_reserve is not None

    loan = (
        await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.project_id == project.id
            )
        )
    ).scalars().first()
    ds_only_reserve = (
        _monthly_pmt(Decimal(str(loan.amount)), Decimal("6.0"), 30)
        * Decimal("6")
    )
    assert Decimal(str(op_reserve.amount)) > ds_only_reserve, (
        f"reserve {op_reserve.amount} should exceed pure-DS "
        f"{ds_only_reserve} — opex branch did not engage"
    )
