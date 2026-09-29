"""The shared test seed earns rent — and the money math on it is right.

``seed_deal_model_with_financials`` used to seed its income stream and OpEx
line with ``active_in_phases=[]`` (the column default), which the engine reads
as "active in no phase". Every test deal built with it computed $0 revenue, so
~90 test files asserted on deals that could not catch a revenue-side bug. The
seed now stamps production's phases (lease-up + stabilized); these tests pin
the revenue side of that seeded deal to numbers derived by hand from the
seeded inputs, NOT copied from engine output.

Seeded inputs (tests/conftest.py):
  8 units x $1,450/mo, 95% stabilized occupancy, rent escalation 3%/yr
  OpEx: property tax $18,000/yr, insurance $9,600/yr, $3,600/unit/yr,
        itemised "Property Management" line $8,640/yr, mgmt fee 8% of EGI,
        capex reserve $600/unit/yr; expense growth 3%/yr
  exit cap 5.5%, no selling costs

With no milestones and no phase months set, the engine's fallback timeline is
acquisition (period 0), major renovation (period 1), stabilized (periods 2..61),
exit (period 62). Every escalator is 3%/yr compounded monthly from period 0:
  g(p) = 1.03 ** (p / 12)

Per stabilized month, before growth:
  GPR  = 8 x 1,450                                   = 11,600.00
  EGI  = 11,600 x 0.95                               = 11,020.00
  OpEx = (18,000 + 9,600 + 3,600 x 8 + 8,640) / 12   =  5,420.00
         + mgmt fee 8% x 11,020                      =    881.60   -> 6,301.60
  Capex reserve = 600 x 8 / 12                       =    400.00
  NOI  = 11,020 - 6,301.60 - 400                     =  4,318.40
and each month's figure is that x g(p).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.engines.waterfall import compute_waterfall
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    WaterfallResult,
    WaterfallTier,
)
from app.models.cashflow import CashFlow, OperationalOutputs, PeriodType
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = pytest.mark.asyncio

_FIRST_STAB = 2
_EXIT = 62
_CENT = Decimal("0.01")


def _g(period: int) -> Decimal:
    """3%/yr growth compounded to ``period`` months."""
    return Decimal("1.03") ** (Decimal(period) / Decimal("12"))


def _close(actual: object, expected: Decimal, tol: Decimal = _CENT) -> bool:
    return abs(Decimal(str(actual)) - expected) <= tol


async def _seed(session: AsyncSession, **kwargs):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Seeded Revenue")
    deal_model, inputs, stream, opex = await seed_deal_model_with_financials(
        session, opp, user, **kwargs
    )
    project = (
        await session.execute(select(Project).where(Project.scenario_id == deal_model.id))
    ).scalar_one()
    return deal_model, project, inputs, stream, opex


async def _rows(session: AsyncSession, deal_model_id) -> list[CashFlow]:
    return list(
        (
            await session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == deal_model_id)
                .order_by(CashFlow.period)
            )
        ).scalars()
    )


async def _outputs(session: AsyncSession, deal_model_id) -> OperationalOutputs:
    return (
        await session.execute(
            select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal_model_id)
        )
    ).scalar_one()


async def test_seed_stamps_production_phases(session: AsyncSession) -> None:
    _dm, _project, _inputs, stream, opex = await _seed(session)
    assert list(stream.active_in_phases) == ["lease_up", "stabilized"]
    assert list(opex.active_in_phases) == ["lease_up", "stabilized"]


async def test_seeded_deal_earns_rent_and_nets_noi(session: AsyncSession) -> None:
    deal_model, *_ = await _seed(session)
    await session.commit()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()

    rows = await _rows(session, deal_model.id)
    assert [r.period_type for r in rows[:3]] == [
        PeriodType.acquisition,
        PeriodType.major_renovation,
        PeriodType.stabilized,
    ]
    assert rows[-1].period == _EXIT and rows[-1].period_type == PeriodType.exit

    # No rent before the building operates: the stream is not active in
    # acquisition or renovation.
    assert Decimal(str(rows[0].gross_revenue)) == 0
    assert Decimal(str(rows[1].gross_revenue)) == 0

    first = rows[_FIRST_STAB]
    g2 = _g(_FIRST_STAB)
    assert _close(first.gross_revenue, Decimal("11600") * g2)
    assert _close(first.vacancy_loss, Decimal("580") * g2)  # 5% of GPR
    assert _close(first.effective_gross_income, Decimal("11020") * g2)
    assert _close(first.operating_expenses, Decimal("6301.60") * g2)
    assert _close(first.capex_reserve, Decimal("400") * g2)
    assert _close(first.noi, Decimal("4318.40") * g2)
    # No debt on this deal: every dollar of NOI is net cash flow.
    assert _close(first.net_cash_flow, Decimal("4318.40") * g2)

    # One year later the whole line has grown exactly 3%.
    later = rows[_FIRST_STAB + 12]
    assert _close(later.noi, Decimal("4318.40") * g2 * Decimal("1.03"))

    outputs = await _outputs(session, deal_model.id)
    # Stabilized NOI = first stabilized month x 12.
    assert _close(outputs.noi_stabilized, Decimal("51820.80") * g2, Decimal("0.05"))

    # Exit: sale = stabilized NOI grown from first stabilization to exit, / 5.5%.
    stab_noi_annual = Decimal("51820.80") * g2
    sale = stab_noi_annual * _g(_EXIT - _FIRST_STAB) / Decimal("0.055")
    exit_row = rows[-1]
    exit_sale = Decimal(str(exit_row.net_cash_flow)) - Decimal(str(exit_row.noi))
    assert _close(exit_sale, sale, Decimal("1.00"))


async def test_opt_out_seeds_a_deal_with_no_revenue(session: AsyncSession) -> None:
    deal_model, _project, _inputs, stream, _opex = await _seed(
        session, active_in_phases=[]
    )
    assert list(stream.active_in_phases) == []
    await session.commit()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()

    rows = await _rows(session, deal_model.id)
    assert all(Decimal(str(r.gross_revenue)) == 0 for r in rows)
    # Only the scalar OpEx remains: tax + insurance + per-unit + capex reserve
    # = (18,000 + 9,600 + 28,800 + 4,800) / 12 = 5,100/mo, and no NOI to cover it.
    assert _close(rows[_FIRST_STAB].noi, Decimal("-5100") * _g(_FIRST_STAB))


async def test_seeded_deal_dscr(session: AsyncSession) -> None:
    deal_model, project, *_ = await _seed(session)
    debt = CapitalModule(
        scenario_id=deal_model.id,
        label="Senior Loan",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": "400000", "interest_rate_pct": 6.0},
        carry={"carry_type": "io_only", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(debt)
    await session.flush()
    session.add(
        CapitalModuleProject(
            capital_module_id=debt.id,
            project_id=project.id,
            amount=Decimal("400000"),
            active_from="acquisition",
            active_to="exit",
            auto_size=False,
        )
    )
    await session.commit()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()

    rows = await _rows(session, deal_model.id)
    # Interest only: 400,000 x 6% / 12 = 2,000/mo.
    monthly_ds = Decimal("2000")
    first = rows[_FIRST_STAB]
    assert _close(first.debt_service, monthly_ds)
    assert _close(first.net_cash_flow, Decimal("4318.40") * _g(_FIRST_STAB) - monthly_ds)

    outputs = await _outputs(session, deal_model.id)
    # DSCR = 51,820.80 x g(2) / 24,000 ~= 2.17 — a positive, bankable ratio,
    # where the zero-revenue seed produced a negative NOI.
    expected_dscr = Decimal("51820.80") * _g(_FIRST_STAB) / (monthly_ds * 12)
    assert _close(outputs.dscr, expected_dscr, Decimal("0.0001"))
    # Debt yield = stabilized NOI / loan = 13.0%.
    expected_dy = Decimal("51820.80") * _g(_FIRST_STAB) / Decimal("400000") * 100
    assert _close(outputs.debt_yield_pct, expected_dy, Decimal("0.001"))


async def test_seeded_deal_waterfall_distributes_the_rent(session: AsyncSession) -> None:
    """All-equity deal, one LP, a 100%-to-LP residual tier: every positive
    month's net cash flow — which is now rent less OpEx — goes to the LP."""
    deal_model, project, *_ = await _seed(session)
    lp = CapitalModule(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        label="LP Equity",
        vehicle_type="equity",
        equity_role="lp",
        stack_position=1,
        source={"amount": "100000"},
        carry={"carry_type": "none", "payment_frequency": "at_exit"},
        exit_terms={"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    session.add(lp)
    await session.flush()
    session.add_all(
        [
            CapitalModuleProject(
                capital_module_id=lp.id,
                project_id=project.id,
                amount=Decimal("100000"),
                active_from="acquisition",
                active_to="exit",
                auto_size=False,
            ),
            WaterfallTier(
                scenario_id=deal_model.id,
                capital_module_id=None,
                priority=1,
                tier_type="residual",
                lp_split_pct=Decimal("100"),
                gp_split_pct=Decimal("0"),
                description="All residual to LP",
            ),
        ]
    )
    await session.commit()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    await compute_waterfall(deal_model.id, session)
    await session.commit()

    results = list(
        (
            await session.execute(
                select(WaterfallResult)
                .where(
                    WaterfallResult.scenario_id == deal_model.id,
                    WaterfallResult.capital_module_id == lp.id,
                )
                .order_by(WaterfallResult.period)
            )
        ).scalars()
    )
    by_period = {r.period: Decimal(str(r.cash_distributed)) for r in results}

    # Acquisition and renovation are cash-negative (tax + insurance, then
    # + per-unit OpEx): capital calls, nothing distributed.
    assert by_period.get(0, Decimal("0")) == 0
    assert by_period.get(1, Decimal("0")) == 0
    # First stabilized month: the LP receives that month's NOI.
    assert _close(by_period[_FIRST_STAB], Decimal("4318.40") * _g(_FIRST_STAB))

    # Over the hold the LP receives every positive month's cash flow.
    rows = await _rows(session, deal_model.id)
    positive_ncf = sum(
        (Decimal(str(r.net_cash_flow)) for r in rows if Decimal(str(r.net_cash_flow)) > 0),
        Decimal("0"),
    )
    assert _close(sum(by_period.values(), Decimal("0")), positive_ncf, Decimal("1.00"))
    assert positive_ncf > Decimal("1000000")  # the exit sale reaches the LP
