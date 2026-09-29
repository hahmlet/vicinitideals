"""Seed for the combined-return (IRR / equity multiple) parity tests.

A deal whose returns can be compared engine-vs-workbook at all needs a
real equity outflow: the earlier seeds had no Uses, so the levered cash
flow never went negative and IRR / EM fell to 0 through IFERROR.

This one buys the seeded 8-unit building for $800k (a ~6.9% going-in
cap on the seed's ~$55k stabilized NOI), funded 100% by an LP equity
module, then runs compute_cash_flows.

Why no debt: the workbook's Levered Cash Flow row adds loan proceeds
at Y0 (the "Debt Proceeds (Y0 draws)" row) but never deducts the loan
payoff at sale, while the engine's per-period net_cash_flow -- what
combined_irr_pct / combined_em_x are computed from -- carries no loan
principal in either direction. With a loan in the deal the two series
differ by construction, so a debt-financed seed cannot show parity. That
disagreement is reported, not papered over here.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
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

PURCHASE_PRICE = Decimal("800000")


async def seed_all_equity_acquisition(session: AsyncSession, *, name: str):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user, name=name)
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    session.add(UseLine(
        project_id=project.id, label="Purchase Price", amount=PURCHASE_PRICE,
        phase="acquisition", cost_category="acquisition",
    ))
    equity = CapitalModule(
        scenario_id=deal_model.id,
        label="LP Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.lp.value,
        stack_position=1,
        source={"amount": str(PURCHASE_PRICE)},
        carry={"carry_type": "none", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition", active_phase_end="exit",
    )
    session.add(equity)
    await session.flush()
    session.add(CapitalModuleProject(
        capital_module_id=equity.id, project_id=project.id,
        amount=PURCHASE_PRICE,
    ))
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


def engine_annual_ncf(ctx: dict) -> list[float]:
    """The engine's per-period net_cash_flow summed into the workbook's
    year buckets (period 0 = Y0, periods 1-12 = Y1, ...), Y0 first."""
    from app.exporters.investor_export import _period_to_year

    buckets: dict[int, Decimal] = {}
    for cfs in ctx["cash_flows"].values():
        for cf in cfs:
            y = _period_to_year(cf.period)
            buckets[y] = buckets.get(y, Decimal(0)) + Decimal(
                str(cf.net_cash_flow or 0)
            )
    return [float(buckets.get(y, 0)) for y in range(0, max(buckets) + 1)]
