from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.engines.waterfall import _allocate_capital_calls, compute_waterfall
from app.engines.waterfall import ModuleState  # noqa: PLC2701
from app.models.capital import CapitalModule, EquityRole, VehicleType, WaterfallResult, WaterfallTier
from app.schemas.capital import CapitalCarrySchema, CapitalExitSchema, CapitalSourceSchema
from app.models.cashflow import CashFlow, OperationalOutputs, PeriodType
from app.models.deal import Scenario, ProjectType
from app.models.org import Organization, User
from app.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)


@pytest.mark.asyncio
async def test_compute_waterfall_persists_results_and_metrics(db_session: AsyncSession) -> None:
    deal = await _seed_base_deal(db_session)

    senior_debt = CapitalModule(
        scenario_id=deal.id,
        label="Senior Construction Loan",
        vehicle_type=VehicleType.debt.value,
        stack_position=1,
        source={"amount": "60000", "interest_rate_pct": 6.0},
        carry={"carry_type": "io_only", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    lp_equity = CapitalModule(
        scenario_id=deal.id,
        label="LP Preferred Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.lp.value,
        stack_position=2,
        source={"amount": "25000", "interest_rate_pct": 8.0},
        carry={"carry_type": "none", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    gp_equity = CapitalModule(
        scenario_id=deal.id,
        label="GP Common Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.gp.value,
        stack_position=3,
        source={"amount": "15000", "interest_rate_pct": 6.0},
        carry={"carry_type": "none", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    db_session.add_all([senior_debt, lp_equity, gp_equity])
    await db_session.flush()

    # Mirror the real pipeline: the cashflow engine owns the CashFlow rows
    # (debt_service, net_cash_flow, cumulative) and the unlevered IRR on the
    # default project's OperationalOutputs row BEFORE the waterfall runs.
    # Since commit b2e6e31 the waterfall no longer overwrites those values —
    # it only reads them (DSCR from row debt_service, levered IRR from NCF).
    from app.models.capital import CapitalModuleProject as _CMP
    from app.models.project import Project as _Project
    _project = _Project(scenario_id=deal.id, name="Waterfall Default Project")
    db_session.add(_project)
    await db_session.flush()
    db_session.add(
        OperationalOutputs(
            scenario_id=deal.id,
            project_id=_project.id,
            project_irr_unlevered=Decimal("5.000000"),
        )
    )
    # Junction coverage: a project without an attached equity module makes
    # the waterfall auto-create a synthetic "Owner Equity" module, which
    # would bump capital_module_count.
    db_session.add_all(
        [
            _CMP(
                capital_module_id=lp_equity.id,
                project_id=_project.id,
                amount=Decimal("25000"),
                active_from="acquisition",
                active_to="exit",
                auto_size=False,
            ),
            _CMP(
                capital_module_id=gp_equity.id,
                project_id=_project.id,
                amount=Decimal("15000"),
                active_from="acquisition",
                active_to="exit",
                auto_size=False,
            ),
        ]
    )

    db_session.add_all(
        [
            WaterfallTier(
                scenario_id=deal.id,
                capital_module_id=senior_debt.id,
                priority=1,
                tier_type="debt_service",
                lp_split_pct=Decimal("0"),
                gp_split_pct=Decimal("0"),
                description="Current-pay debt service and payoff",
            ),
            WaterfallTier(
                scenario_id=deal.id,
                capital_module_id=lp_equity.id,
                priority=2,
                tier_type="pref_return",
                lp_split_pct=Decimal("100"),
                gp_split_pct=Decimal("0"),
                description="8% LP pref",
            ),
            WaterfallTier(
                scenario_id=deal.id,
                capital_module_id=lp_equity.id,
                priority=3,
                tier_type="return_of_equity",
                lp_split_pct=Decimal("100"),
                gp_split_pct=Decimal("0"),
                description="Return LP capital",
            ),
            WaterfallTier(
                scenario_id=deal.id,
                capital_module_id=gp_equity.id,
                priority=4,
                tier_type="return_of_equity",
                lp_split_pct=Decimal("0"),
                gp_split_pct=Decimal("100"),
                description="Return GP capital",
            ),
            WaterfallTier(
                scenario_id=deal.id,
                capital_module_id=None,
                priority=5,
                tier_type="residual",
                lp_split_pct=Decimal("70"),
                gp_split_pct=Decimal("30"),
                description="70/30 residual split",
            ),
        ]
    )

    db_session.add_all(
        [
            CashFlow(
                scenario_id=deal.id,
                project_id=_project.id,
                period=0,
                period_type=PeriodType.acquisition.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("-100000"),
                cumulative_cash_flow=Decimal("-100000"),
            ),
            # io_only PMT on the $60k senior loan: 60000 × 6% / 12 = $300/mo.
            # The cashflow engine writes DS + post-DS NCF; the waterfall reads
            # them as-is (b2e6e31 removed the in-place overwrite).
            CashFlow(
                scenario_id=deal.id,
                project_id=_project.id,
                period=1,
                period_type=PeriodType.stabilized.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("3500"),
                debt_service=Decimal("300"),
                net_cash_flow=Decimal("3200"),
                cumulative_cash_flow=Decimal("-96800"),
            ),
            CashFlow(
                scenario_id=deal.id,
                project_id=_project.id,
                period=2,
                period_type=PeriodType.stabilized.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("4500"),
                debt_service=Decimal("300"),
                net_cash_flow=Decimal("4200"),
                cumulative_cash_flow=Decimal("-92600"),
            ),
            CashFlow(
                scenario_id=deal.id,
                project_id=_project.id,
                period=3,
                period_type=PeriodType.exit.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("180000"),
                cumulative_cash_flow=Decimal("87400"),
            ),
        ]
    )
    await db_session.commit()

    summary = await compute_waterfall(deal.id, db_session)
    await db_session.commit()

    rows = list(
        (
            await db_session.execute(
                select(WaterfallResult)
                .where(WaterfallResult.scenario_id == deal.id)
                .order_by(WaterfallResult.period.asc())
            )
        ).scalars()
    )
    updated_cash_flows = list(
        (
            await db_session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == deal.id)
                .order_by(CashFlow.period.asc())
            )
        ).scalars()
    )
    outputs = (
        await db_session.execute(
            select(OperationalOutputs).where(OperationalOutputs.scenario_id == deal.id)
        )
    ).scalar_one()

    assert summary["deal_model_id"] == str(deal.id)
    assert summary["waterfall_result_count"] == len(rows)
    assert summary["capital_module_count"] == 3
    assert summary["waterfall_tier_count"] == 5
    assert summary["lp_irr_pct"] is not None
    assert summary["gp_irr_pct"] is not None
    assert summary["equity_multiple"] > Decimal("1.000000")
    assert summary["cash_on_cash_year_1_pct"] > Decimal("0")
    assert summary["dscr"] > Decimal("0")
    assert summary["project_irr_levered"] is not None
    assert Decimal(str(outputs.dscr)) == Decimal(str(summary["dscr"]))
    assert Decimal(str(outputs.project_irr_levered)) == Decimal(
        str(summary["project_irr_levered"])
    )
    assert Decimal(str(outputs.project_irr_levered)) != Decimal(
        str(outputs.project_irr_unlevered)
    )

    debt_rows = [row for row in rows if row.capital_module_id == senior_debt.id]
    lp_rows = [row for row in rows if row.capital_module_id == lp_equity.id]
    gp_rows = [row for row in rows if row.capital_module_id == gp_equity.id]
    exit_rows = [row for row in rows if row.period == 3]

    assert sum((Decimal(str(row.cash_distributed)) for row in debt_rows), Decimal("0")) > Decimal(
        "60000"
    )
    assert sum((Decimal(str(row.cash_distributed)) for row in lp_rows), Decimal("0")) > Decimal(
        "25000"
    )
    assert sum((Decimal(str(row.cash_distributed)) for row in gp_rows), Decimal("0")) > Decimal(
        "15000"
    )
    assert any(row.party_irr_pct is not None for row in exit_rows)
    # Since commit b2e6e31 the cashflow engine is authoritative for
    # debt_service / net_cash_flow / cumulative_cash_flow: the waterfall must
    # NOT rewrite the rows it read (the old overwrite corrupted DSCR by
    # replacing the PMT with the residual NCF allocation).
    assert Decimal(str(updated_cash_flows[1].debt_service)) == Decimal("300")
    assert Decimal(str(updated_cash_flows[2].debt_service)) == Decimal("300")
    assert Decimal(str(updated_cash_flows[3].debt_service)) == Decimal("0")
    assert Decimal(str(updated_cash_flows[1].net_cash_flow)) == Decimal("3200")
    assert Decimal(str(updated_cash_flows[2].net_cash_flow)) == Decimal("4200")
    # DSCR from the engine-authored rows: annualized median NOI (4000×12)
    # over annualized median DS (300×12) = 13.333333.
    assert Decimal(str(summary["dscr"])) == Decimal("13.333333")


@pytest.mark.asyncio
async def test_irr_hurdle_split_waits_until_lp_hurdle_is_met(db_session: AsyncSession) -> None:
    deal = await _seed_base_deal(db_session)

    lp_equity = CapitalModule(
        scenario_id=deal.id,
        label="LP Preferred Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.lp.value,
        stack_position=1,
        source={"amount": "80000", "interest_rate_pct": 8.0},
        carry={"carry_type": "none", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    gp_equity = CapitalModule(
        scenario_id=deal.id,
        label="GP Common Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.gp.value,
        stack_position=2,
        source={"amount": "20000", "interest_rate_pct": 6.0},
        carry={"carry_type": "none", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    db_session.add_all([lp_equity, gp_equity])
    await db_session.flush()

    return_lp = WaterfallTier(
        scenario_id=deal.id,
        capital_module_id=lp_equity.id,
        priority=1,
        tier_type="return_of_equity",
        lp_split_pct=Decimal("100"),
        gp_split_pct=Decimal("0"),
        description="Return LP capital first",
    )
    return_gp = WaterfallTier(
        scenario_id=deal.id,
        capital_module_id=gp_equity.id,
        priority=2,
        tier_type="return_of_equity",
        lp_split_pct=Decimal("0"),
        gp_split_pct=Decimal("100"),
        description="Then return GP capital",
    )
    hurdle_split = WaterfallTier(
        scenario_id=deal.id,
        capital_module_id=None,
        priority=3,
        tier_type="irr_hurdle_split",
        irr_hurdle_pct=Decimal("15.000000"),
        lp_split_pct=Decimal("70.000000"),
        gp_split_pct=Decimal("30.000000"),
        description="70/30 only after LP clears 15% IRR",
    )
    db_session.add_all([return_lp, return_gp, hurdle_split])

    db_session.add_all(
        [
            CashFlow(
                scenario_id=deal.id,
                period=0,
                period_type=PeriodType.acquisition.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("-100000"),
                cumulative_cash_flow=Decimal("-100000"),
            ),
            CashFlow(
                scenario_id=deal.id,
                period=1,
                period_type=PeriodType.stabilized.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("5000"),
                cumulative_cash_flow=Decimal("-95000"),
            ),
            CashFlow(
                scenario_id=deal.id,
                period=2,
                period_type=PeriodType.stabilized.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("120000"),
                cumulative_cash_flow=Decimal("25000"),
            ),
            CashFlow(
                scenario_id=deal.id,
                period=3,
                period_type=PeriodType.exit.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("0"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("20000"),
                cumulative_cash_flow=Decimal("45000"),
            ),
        ]
    )
    await db_session.commit()

    summary = await compute_waterfall(deal.id, db_session)
    await db_session.commit()

    rows = list(
        (
            await db_session.execute(
                select(WaterfallResult)
                .where(WaterfallResult.scenario_id == deal.id)
                .order_by(WaterfallResult.period.asc())
            )
        ).scalars()
    )

    gp_period_2_split = next(
        row
        for row in rows
        if row.period == 2
        and row.tier_id == hurdle_split.id
        and row.capital_module_id == gp_equity.id
    )
    gp_period_3_split = next(
        row
        for row in rows
        if row.period == 3
        and row.tier_id == hurdle_split.id
        and row.capital_module_id == gp_equity.id
    )

    assert summary["lp_irr_pct"] is not None
    assert summary["gp_irr_pct"] is not None
    assert Decimal(str(gp_period_2_split.cash_distributed)) == Decimal("0.000000")
    assert Decimal(str(gp_period_3_split.cash_distributed)) > Decimal("0.000000")


async def _seed_base_deal(session: AsyncSession) -> Scenario:
    from app.models.deal import Deal
    org = Organization(id=uuid4(), name="Test Org", slug=f"test-org-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Test User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name=f"Waterfall Test Opportunity {uuid4().hex[:6]}",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        source_url=f"manual://{uuid4().hex}",
        created_by_user_id=user.id,
    )
    top_deal = Deal(id=uuid4(), org_id=org.id, name="Base Case", created_by_user_id=user.id)
    deal = Scenario(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Base Case",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add_all([org, user, opportunity, top_deal, deal])
    await session.flush()
    return deal


# ---------------------------------------------------------------------------
# Unit tests for _allocate_capital_calls (pure function, no DB required)
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")
_MONEY_PLACES = Decimal("0.000001")


def _make_equity_state(
    equity_role: EquityRole,
    stack_position: int,
    commitment: Decimal = _ZERO,
) -> ModuleState:
    module = CapitalModule(
        id=uuid4(),
        vehicle_type=VehicleType.equity.value,
        equity_role=equity_role.value,
        stack_position=stack_position,
        label=f"Equity {stack_position}",
        active_phase_start=None,
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
    )
    return ModuleState(
        module=module,
        source=CapitalSourceSchema.model_validate({}),
        carry=CapitalCarrySchema.model_validate({"carry_type": "none"}),
        exit_terms=CapitalExitSchema.model_validate({"exit_type": "full_payoff", "trigger": "sale"}),
        commitment=commitment,
    )


@pytest.mark.unit
def test_single_uncapped_equity_absorbs_full_call() -> None:
    state = _make_equity_state(EquityRole.gp, stack_position=1)
    allocs = _allocate_capital_calls(
        Decimal("1000000"), "construction", [state]
    )
    assert allocs[state.module.id] == Decimal("1000000").quantize(_MONEY_PLACES)
    assert state.outstanding_principal == Decimal("1000000").quantize(_MONEY_PLACES)


@pytest.mark.unit
def test_two_uncapped_equity_modules_split_pro_rata() -> None:
    lp = _make_equity_state(EquityRole.lp, stack_position=1)
    gp = _make_equity_state(EquityRole.gp, stack_position=2)
    allocs = _allocate_capital_calls(
        Decimal("1000000"), "construction", [lp, gp]
    )
    half = Decimal("500000").quantize(_MONEY_PLACES)
    assert allocs[lp.module.id] == half, "LP should get half of uncapped call"
    assert allocs[gp.module.id] == half, "GP should get half of uncapped call"
    assert lp.outstanding_principal == half
    assert gp.outstanding_principal == half


@pytest.mark.unit
def test_capped_lp_fills_first_uncapped_gp_absorbs_residual() -> None:
    lp = _make_equity_state(
        EquityRole.lp, stack_position=1, commitment=Decimal("2000000")
    )
    gp = _make_equity_state(EquityRole.gp, stack_position=2)
    allocs = _allocate_capital_calls(
        Decimal("2500000"), "construction", [lp, gp]
    )
    assert allocs[lp.module.id] == Decimal("2000000").quantize(_MONEY_PLACES)
    assert allocs[gp.module.id] == Decimal("500000").quantize(_MONEY_PLACES)


# ---------------------------------------------------------------------------
# Phase B — Deferred Dev Fee balance integration tests
# ---------------------------------------------------------------------------


async def _seed_project_with_auto_dev_fee(
    session: AsyncSession,
    deal: Scenario,
    *,
    deferred: str,
) -> None:
    """Attach a Project + auto-Dev-Fee UseLine (+ DDF capital module) to a scenario.

    `deferred` is stored as a string on the auto Dev Fee row's
    `dev_fee_binding_context`, matching engine-written shape. Since commit
    cf21d10 the waterfall reads the DDF opening balance from the
    `deferred_developer_fee` capital module's source amount (what was actually
    contributed as a source), NOT from the binding context — so when
    `deferred` > 0 we also seed the DDF module the sizer would have written.
    """
    from app.models.deal import UseLine
    from app.models.project import Project

    project = Project(
        id=uuid4(),
        scenario_id=deal.id,
        name="Phase B Test Project",
    )
    session.add(project)
    await session.flush()

    auto_line = UseLine(
        id=uuid4(),
        project_id=project.id,
        label="Developer Fee (auto)",
        amount=Decimal("50000"),
        cost_category="Soft Costs / Fees",
        is_auto_dev_fee=True,
        dev_fee_binding_context={
            "deferred": deferred,
            "funded_at_close": "40000",
        },
    )
    session.add(auto_line)
    if Decimal(deferred) > Decimal("0"):
        session.add(
            CapitalModule(
                scenario_id=deal.id,
                label="Deferred Developer Fee",
                vehicle_type=VehicleType.deferred_developer_fee.value,
                stack_position=99,
                source={"amount": deferred},
                carry={"carry_type": "none"},
                exit_terms={"exit_type": "profit_share", "trigger": "ongoing"},
                active_phase_start="acquisition",
                active_phase_end="exit",
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_phase_b_deferred_dev_fee_balance_drains_via_waterfall(
    db_session: AsyncSession,
) -> None:
    """Auto-seeds a deferred_developer_fee tier when balance > 0, then
    drains the balance from operating cash and persists the schedule."""
    deal = await _seed_base_deal(db_session)
    await _seed_project_with_auto_dev_fee(db_session, deal, deferred="10000")

    db_session.add(
        CapitalModule(
            scenario_id=deal.id,
            label="GP Common Equity",
            vehicle_type=VehicleType.equity.value,
            equity_role=EquityRole.gp.value,
            stack_position=1,
            source={"amount": "1"},
            carry={"carry_type": "none"},
            exit_terms={"exit_type": "profit_share", "trigger": "ongoing"},
            active_phase_start="acquisition",
            active_phase_end="exit",
        )
    )
    db_session.add_all(
        [
            CashFlow(
                scenario_id=deal.id,
                period=p,
                period_type=PeriodType.stabilized.value,
                gross_revenue=Decimal("0"),
                vacancy_loss=Decimal("0"),
                effective_gross_income=Decimal("0"),
                operating_expenses=Decimal("0"),
                capex_reserve=Decimal("0"),
                noi=Decimal("4000"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("4000"),
                cumulative_cash_flow=Decimal("0"),
            )
            for p in range(1, 6)
        ]
    )
    await db_session.commit()

    await compute_waterfall(deal.id, db_session)
    await db_session.commit()

    # Auto-seeded tier
    tiers = list(
        (
            await db_session.execute(
                select(WaterfallTier).where(WaterfallTier.scenario_id == deal.id)
            )
        ).scalars()
    )
    deferred_tiers = [
        t for t in tiers if str(t.tier_type) == "deferred_developer_fee"
    ]
    assert len(deferred_tiers) == 1
    assert deferred_tiers[0].capital_module_id is None

    # Balance schedule persisted on default OO row
    outputs = (
        await db_session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == deal.id
            )
        )
    ).scalar_one()
    series = outputs.dev_fee_balance_series
    assert series is not None
    assert series["opening_at_close"] == "10000.000000"
    # 5 periods × $4000 = $20k > $10k → fully paid within window
    assert series["fully_paid_period"] is not None
    assert series["fully_paid_period"] <= 5
    # Closing balance at end is zero.
    assert series["periods"][-1]["closing_balance"] == "0.000000"


@pytest.mark.asyncio
async def test_phase_b_no_deferred_balance_skips_tier_and_clears_series(
    db_session: AsyncSession,
) -> None:
    """When the scenario has no deferred Dev Fee balance, the waterfall
    must not auto-seed the tier and must write None to clear stale data."""
    deal = await _seed_base_deal(db_session)
    await _seed_project_with_auto_dev_fee(db_session, deal, deferred="0")

    db_session.add(
        CapitalModule(
            scenario_id=deal.id,
            label="GP Common Equity",
            vehicle_type=VehicleType.equity.value,
            equity_role=EquityRole.gp.value,
            stack_position=1,
            source={"amount": "1"},
            carry={"carry_type": "none"},
            exit_terms={"exit_type": "profit_share", "trigger": "ongoing"},
            active_phase_start="acquisition",
            active_phase_end="exit",
        )
    )
    db_session.add(
        CashFlow(
            scenario_id=deal.id,
            period=1,
            period_type=PeriodType.stabilized.value,
            gross_revenue=Decimal("0"),
            vacancy_loss=Decimal("0"),
            effective_gross_income=Decimal("0"),
            operating_expenses=Decimal("0"),
            capex_reserve=Decimal("0"),
            noi=Decimal("4000"),
            debt_service=Decimal("0"),
            net_cash_flow=Decimal("4000"),
            cumulative_cash_flow=Decimal("0"),
        )
    )
    await db_session.commit()

    await compute_waterfall(deal.id, db_session)
    await db_session.commit()

    tiers = list(
        (
            await db_session.execute(
                select(WaterfallTier).where(WaterfallTier.scenario_id == deal.id)
            )
        ).scalars()
    )
    assert not [
        t for t in tiers if str(t.tier_type) == "deferred_developer_fee"
    ]
    outputs = (
        await db_session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == deal.id
            )
        )
    ).scalar_one()
    assert outputs.dev_fee_balance_series is None
