from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vicinitideals.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs, PeriodType
from vicinitideals.models.deal import (
    DealModel,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
)
from vicinitideals.models.org import Organization, User
from vicinitideals.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
    Project,
)

from vicinitideals.engines.cashflow import PhaseSpec, _build_phase_plan, _compute_period, compute_cash_flows


# ---------------------------------------------------------------------------
# Shared in-memory DB fixture (mirrors conftest.py pattern for engine tests
# that need a local, self-contained setup without the shared session-scoped engine)
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    from vicinitideals.models import Base  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Integration test — compute_cash_flows against in-memory DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_compute_cash_flows_generates_rows_and_outputs(db_session: AsyncSession) -> None:
    deal_id = await _seed_cashflow_deal(db_session)

    summary = await compute_cash_flows(deal_model_id=deal_id, session=db_session)
    await db_session.commit()

    cash_flows = list(
        (
            await db_session.execute(
                select(CashFlow)
                .where(CashFlow.scenario_id == deal_id)
                .order_by(CashFlow.period.asc())
            )
        ).scalars()
    )
    line_items = list(
        (
            await db_session.execute(
                select(CashFlowLineItem).where(
                    CashFlowLineItem.scenario_id == deal_id
                )
            )
        ).scalars()
    )
    outputs = (
        await db_session.execute(
            select(OperationalOutputs).where(
                OperationalOutputs.scenario_id == deal_id
            )
        )
    ).scalar_one()

    assert summary["deal_model_id"] == str(deal_id)
    assert summary["cash_flow_count"] == len(cash_flows)
    assert summary["line_item_count"] == len(line_items)
    assert summary["cash_flow_count"] > 0
    assert summary["line_item_count"] >= summary["cash_flow_count"]

    assert outputs.total_timeline_months == len(cash_flows)
    assert Decimal(str(outputs.total_project_cost)) > Decimal("0")
    assert Decimal(str(outputs.equity_required)) > Decimal("0")
    assert outputs.noi_stabilized is not None
    assert outputs.project_irr_unlevered is not None

    assert cash_flows[0].period == 0
    assert cash_flows[-1].period_type == "exit"
    assert any(item.category == "income" for item in line_items)
    assert any(item.category == "expense" for item in line_items)


# ---------------------------------------------------------------------------
# Unit tests — pure functions, no DB
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_phase_plan_major_reno_sequence() -> None:
    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=12,
        hold_phase_enabled=True,
        hold_months=2,
        renovation_months=6,
        lease_up_months=4,
        hold_period_years=Decimal("2.000000"),
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
    )

    phases = _build_phase_plan("acquisition_major_reno", inputs)

    assert [phase.period_type for phase in phases] == [
        PeriodType.acquisition,
        PeriodType.hold,
        PeriodType.major_renovation,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    ]
    assert [phase.months for phase in phases] == [1, 2, 6, 4, 24, 1]


@pytest.mark.unit
def test_build_phase_plan_uses_milestone_dates_for_new_construction() -> None:
    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=24,
        entitlement_months=9,
        construction_months=18,
        lease_up_months=5,
        hold_period_years=Decimal("7.000000"),
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
        milestone_dates={
            "pre_construction_start": "2026-01-01",
            "construction_start": "2026-03-01",
            "lease_up_start": "2026-08-15",
            "stabilized_start": "2026-11-14",
            "exit_date": "2027-11-14",
        },
    )

    phases = _build_phase_plan("new_construction", inputs)

    assert [phase.period_type for phase in phases] == [
        PeriodType.acquisition,
        PeriodType.pre_construction,
        PeriodType.construction,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    ]
    assert [phase.months for phase in phases] == [1, 2, 6, 3, 12, 1]


@pytest.mark.unit
def test_build_phase_plan_falls_back_when_some_milestones_are_missing() -> None:
    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=12,
        hold_phase_enabled=True,
        hold_months=2,
        renovation_months=6,
        lease_up_months=4,
        hold_period_years=Decimal("5.000000"),
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
        milestone_dates={
            "stabilized_start": "2027-05-20",
            "exit_date": "2028-01-01",
        },
    )

    phases = _build_phase_plan("acquisition_major_reno", inputs)

    assert [phase.period_type for phase in phases] == [
        PeriodType.acquisition,
        PeriodType.hold,
        PeriodType.major_renovation,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    ]
    assert [phase.months for phase in phases] == [1, 2, 6, 4, 8, 1]


@pytest.mark.unit
def test_compute_period_includes_itemized_operating_expense_lines() -> None:
    project_id = uuid4()
    deal_model_id = uuid4()
    inputs = OperationalInputs(
        project_id=project_id,
        unit_count_new=10,
        initial_occupancy_pct=Decimal("90.000000"),
        opex_per_unit_annual=Decimal("120.000000"),
        expense_growth_rate_pct_annual=Decimal("4.000000"),
        mgmt_fee_pct=Decimal("0.000000"),
        property_tax_annual=Decimal("0.000000"),
        insurance_annual=Decimal("0.000000"),
        capex_reserve_per_unit_annual=Decimal("0.000000"),
        hold_period_years=Decimal("1.000000"),
        exit_cap_rate_pct=Decimal("5.000000"),
        selling_costs_pct=Decimal("2.000000"),
    )
    expense_lines = [
        OperatingExpenseLine(
            project_id=project_id,
            label="Electric",
            annual_amount=Decimal("1200.000000"),
            escalation_rate_pct_annual=Decimal("5.000000"),
            active_in_phases=["stabilized", "exit"],
        ),
        OperatingExpenseLine(
            project_id=project_id,
            label="Water/Sewer",
            annual_amount=Decimal("2400.000000"),
            escalation_rate_pct_annual=Decimal("0.000000"),
            active_in_phases=["stabilized", "exit"],
        ),
        OperatingExpenseLine(
            project_id=project_id,
            label="Internet",
            annual_amount=Decimal("600.000000"),
            escalation_rate_pct_annual=Decimal("12.000000"),
            active_in_phases=["stabilized", "exit"],
        ),
    ]

    result = _compute_period(
        deal_model_id=deal_model_id,
        period=12,
        phase=PhaseSpec(PeriodType.stabilized, 12),
        month_index=0,
        inputs=inputs,
        streams=[],
        expense_lines=expense_lines,
        stabilized_noi_monthly=None,
    )

    assert result["operating_expenses"] == Decimal("465.000000")
    expense_rows = {
        item.label: Decimal(str(item.net_amount))
        for item in result["line_items"]
        if item.category == "expense"
    }
    assert expense_rows["Operating Expenses"] == Decimal("104.000000")
    assert expense_rows["Electric"] == Decimal("105.000000")
    assert expense_rows["Water/Sewer"] == Decimal("200.000000")
    assert expense_rows["Internet"] == Decimal("56.000000")


# ---------------------------------------------------------------------------
# Seed helper — creates full deal hierarchy for integration test
# ---------------------------------------------------------------------------

async def _seed_cashflow_deal(session: AsyncSession) -> UUID:
    """Create a minimal but complete deal hierarchy for cashflow engine tests."""
    org = Organization(id=uuid4(), name="Test Org", slug=f"test-org-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Test User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name="619 NE 190th Ave, 12-unit reno",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    from vicinitideals.models.deal import Deal, DealOpportunity
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

    project = Project(
        id=uuid4(),
        scenario_id=deal.id,
        opportunity_id=opportunity.id,
        name="12-unit Major Reno",
        deal_type=ProjectType.acquisition_major_reno.value,
    )
    session.add(project)
    await session.flush()

    inputs = OperationalInputs(
        project_id=project.id,
        unit_count_existing=12,
        unit_count_new=12,
        purchase_price=Decimal("1800000"),
        closing_costs_pct=Decimal("2.000000"),
        hold_phase_enabled=True,
        hold_months=2,
        hold_vacancy_rate_pct=Decimal("8.000000"),
        renovation_cost_total=Decimal("360000"),
        renovation_months=6,
        lease_up_months=4,
        initial_occupancy_pct=Decimal("55.000000"),
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        hold_period_years=Decimal("2.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
        income_reduction_pct_during_reno=Decimal("35.000000"),
    )
    rent = IncomeStream(
        project_id=project.id,
        stream_type="residential_rent",
        label="12 Residential Units",
        unit_count=12,
        amount_per_unit_monthly=Decimal("1450.000000"),
        stabilized_occupancy_pct=Decimal("95.000000"),
        escalation_rate_pct_annual=Decimal("3.000000"),
        active_in_phases=["hold", "major_renovation", "lease_up", "stabilized", "exit"],
    )
    laundry = IncomeStream(
        project_id=project.id,
        stream_type="laundry",
        label="Laundry",
        amount_fixed_monthly=Decimal("250.000000"),
        stabilized_occupancy_pct=Decimal("100.000000"),
        escalation_rate_pct_annual=Decimal("2.000000"),
        active_in_phases=["hold", "lease_up", "stabilized", "exit"],
    )

    session.add_all([inputs, rent, laundry])
    await session.flush()
    return deal.id
