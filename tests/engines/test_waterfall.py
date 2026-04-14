from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vicinitideals.engines.waterfall import compute_waterfall
from vicinitideals.models.capital import CapitalModule, FunderType, WaterfallResult, WaterfallTier
from vicinitideals.models.cashflow import CashFlow, OperationalOutputs, PeriodType
from vicinitideals.models.deal import DealModel, ProjectType
from vicinitideals.models.org import Organization, User
from vicinitideals.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    from vicinitideals.models import Base  # noqa: F401 — ensures all tables are registered

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_compute_waterfall_persists_results_and_metrics(db_session: AsyncSession) -> None:
    deal = await _seed_base_deal(db_session)

    senior_debt = CapitalModule(
        scenario_id=deal.id,
        label="Senior Construction Loan",
        funder_type=FunderType.senior_debt.value,
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
        funder_type=FunderType.preferred_equity.value,
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
        funder_type=FunderType.common_equity.value,
        stack_position=3,
        source={"amount": "15000", "interest_rate_pct": 6.0},
        carry={"carry_type": "none", "payment_frequency": "monthly", "capitalized": False},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition",
        active_phase_end="exit",
    )
    db_session.add_all([senior_debt, lp_equity, gp_equity])
    await db_session.flush()

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
                noi=Decimal("3500"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("3500"),
                cumulative_cash_flow=Decimal("-96500"),
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
                noi=Decimal("4500"),
                debt_service=Decimal("0"),
                net_cash_flow=Decimal("4500"),
                cumulative_cash_flow=Decimal("-92000"),
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
                net_cash_flow=Decimal("180000"),
                cumulative_cash_flow=Decimal("88000"),
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
    assert Decimal(str(updated_cash_flows[1].debt_service)) > Decimal("0")
    assert Decimal(str(updated_cash_flows[2].debt_service)) > Decimal("0")
    assert Decimal(str(updated_cash_flows[3].debt_service)) > Decimal("60000")
    assert Decimal(str(updated_cash_flows[1].net_cash_flow)) < Decimal("3500")
    assert Decimal(str(updated_cash_flows[2].net_cash_flow)) < Decimal("4500")


@pytest.mark.asyncio
async def test_irr_hurdle_split_waits_until_lp_hurdle_is_met(db_session: AsyncSession) -> None:
    deal = await _seed_base_deal(db_session)

    lp_equity = CapitalModule(
        scenario_id=deal.id,
        label="LP Preferred Equity",
        funder_type=FunderType.preferred_equity.value,
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
        funder_type=FunderType.common_equity.value,
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


async def _seed_base_deal(session: AsyncSession) -> DealModel:
    from vicinitideals.models.deal import Deal, DealOpportunity
    org = Organization(id=uuid4(), name="Test Org", slug=f"test-org-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Test User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name=f"Waterfall Test Opportunity {uuid4().hex[:6]}",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    top_deal = Deal(id=uuid4(), org_id=org.id, name="Base Case", created_by_user_id=user.id)
    deal = DealModel(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Base Case",
        version=1,
        is_active=True,
        project_type=ProjectType.acquisition_major_reno,
    )
    session.add_all([org, user, opportunity, top_deal, deal])
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))
    await session.flush()
    return deal
