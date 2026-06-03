from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.cashflow import CashFlow, CashFlowLineItem, OperationalOutputs, PeriodType
from app.models.deal import (
    DealModel,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
)
from app.models.org import Organization, User
from app.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
    Project,
)

from app.engines.cashflow import (
    PhaseSpec,
    _build_phase_plan,
    _compute_period,
    _compute_preop_carry_cost,
    _constr_phase_rate_pct,
    _ir_lease_up_pool,
    _op_phase_rate_and_amort,
    _resolve_horizon_months,
    _schedule_preop_months,
    _scheduled_operation_ds,
    _sum_ir_lease_up_interest,
    compute_cash_flows,
)


# ---------------------------------------------------------------------------
# Lightweight stand-ins for capital modules / milestones — avoid SQLAlchemy
# round-trips for pure resolver unit tests.
# ---------------------------------------------------------------------------

class _FakeModule:
    def __init__(self, vehicle_type: str, hold_term_years: int | None = None,
                 amort_term_years: int | None = None) -> None:
        self.vehicle_type = vehicle_type
        src: dict[str, object] = {}
        if hold_term_years is not None:
            src["hold_term_years"] = hold_term_years
        if amort_term_years is not None:
            src["amort_term_years"] = amort_term_years
        self.source = src
        self.carry = {}


class _FakeMilestone:
    def __init__(self, milestone_type: str, duration_days: int = 0) -> None:
        self.milestone_type = milestone_type
        self.duration_days = duration_days


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
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
    )

    phases = _build_phase_plan(
        "value_add",
        inputs,
        capital_modules=[_FakeModule("debt", hold_term_years=2)],
    )

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

    phases = _build_phase_plan("value_add", inputs)

    assert [phase.period_type for phase in phases] == [
        PeriodType.acquisition,
        PeriodType.hold,
        PeriodType.major_renovation,
        PeriodType.lease_up,
        PeriodType.stabilized,
        PeriodType.exit,
    ]
    assert [phase.months for phase in phases] == [1, 2, 6, 4, 8, 1]


# ---------------------------------------------------------------------------
# Horizon resolver tests — replace deal-level hold_period_years with per-loan
# hold_term_years + operation_stabilized milestone fallback.
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_resolve_horizon_single_perm_loan() -> None:
    months, src = _resolve_horizon_months(
        capital_modules=[_FakeModule("debt", hold_term_years=25)],
        orm_milestones=None,
    )
    assert months == 300
    assert src == "perm_debt_hold_term"


@pytest.mark.unit
def test_resolve_horizon_multi_perm_takes_max() -> None:
    months, src = _resolve_horizon_months(
        capital_modules=[
            _FakeModule("debt", hold_term_years=10),
            _FakeModule("debt", hold_term_years=25),
        ],
        orm_milestones=None,
    )
    assert months == 300
    assert src == "perm_debt_hold_term"


@pytest.mark.unit
def test_resolve_horizon_all_cash_uses_stabilized_milestone() -> None:
    months, src = _resolve_horizon_months(
        capital_modules=[],
        orm_milestones=[
            _FakeMilestone("operation_stabilized", duration_days=72 * 30),
        ],
    )
    assert months == 72
    assert src == "operation_stabilized_milestone"


@pytest.mark.unit
def test_resolve_horizon_no_perm_no_stabilized_milestone_falls_back() -> None:
    months, src = _resolve_horizon_months(
        capital_modules=[_FakeModule("equity")],
        orm_milestones=None,
    )
    assert months == 60
    assert src == "fallback_default_60mo"


@pytest.mark.unit
def test_resolve_horizon_construction_loan_alone_falls_back() -> None:
    """Construction loans don't carry hold_term_years (perm-debt scope only)."""
    months, src = _resolve_horizon_months(
        capital_modules=[_FakeModule("construction_loan")],
        orm_milestones=[
            _FakeMilestone("operation_stabilized", duration_days=120 * 30),
        ],
    )
    assert months == 120
    assert src == "operation_stabilized_milestone"


@pytest.mark.unit
def test_build_phase_plan_horizon_from_perm_debt_when_no_milestone_dates() -> None:
    """Horizon resolver feeds stabilized phase length when no exit milestone."""
    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=10,
        opex_per_unit_annual=Decimal("4800.000000"),
        expense_growth_rate_pct_annual=Decimal("3.000000"),
        mgmt_fee_pct=Decimal("4.000000"),
        property_tax_annual=Decimal("18000.000000"),
        insurance_annual=Decimal("7200.000000"),
        capex_reserve_per_unit_annual=Decimal("300.000000"),
        exit_cap_rate_pct=Decimal("5.750000"),
        selling_costs_pct=Decimal("2.500000"),
    )
    phases = _build_phase_plan(
        "acquisition",
        inputs,
        capital_modules=[_FakeModule("debt", hold_term_years=10)],
    )
    stabilized = next(p for p in phases if p.period_type == PeriodType.stabilized)
    assert stabilized.months == 120  # 10y × 12mo


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
        source_url=f"manual://{uuid4().hex}",
        created_by_user_id=user.id,
    )
    from app.models.deal import Deal
    top_deal = Deal(id=uuid4(), org_id=org.id, name="Base Case", created_by_user_id=user.id)
    deal = DealModel(
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

    project = Project(
        id=uuid4(),
        scenario_id=deal.id,
        opportunity_id=opportunity.id,
        name="12-unit Major Reno",
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


class _ScheduledCarryModule:
    """Lightweight stand-in for a debt CapitalModule with carry.schedule."""

    def __init__(self, *, schedule: list[dict], amount: str = "1500000",
                 rate_pct: float | None = 6.0) -> None:
        self.id = uuid4()
        self.source = {"amount": amount, "interest_rate_pct": rate_pct}
        self.carry = {"schedule": schedule}


@pytest.mark.unit
def test_scheduled_operation_ds_includes_pi_phase() -> None:
    """Regression: debt with carry.schedule (IR→PI bond) was excluded from the
    operation-phase debt-service aggregate, producing DSCR = NOI/0 = 0 and
    breaking the dual-constraint sizing loop. The new helper sums the
    operation-phase PI payment from each scheduled module."""
    bond = _ScheduledCarryModule(
        schedule=[
            {
                "label": "IR",
                "carry_type": "interest_reserve",
                "duration": {"type": "months", "months": 6},
                "rate_pct": 6.0,
            },
            {
                "label": "PI",
                "carry_type": "pi",
                "duration": {"type": "remainder"},
                "rate_pct": 6.0,
                "amort_term_years": 30,
            },
        ],
        amount="1500000",
    )

    ds = _scheduled_operation_ds([bond], {bond.id})

    # PMT(1.5M, 6%/yr, 30yr) ≈ $8,991/mo
    assert ds > Decimal("8900")
    assert ds < Decimal("9100")


@pytest.mark.unit
def test_scheduled_operation_ds_skips_modules_not_in_set() -> None:
    bond = _ScheduledCarryModule(
        schedule=[
            {"carry_type": "pi", "duration": {"type": "remainder"},
             "rate_pct": 6.0, "amort_term_years": 30},
        ],
    )

    assert _scheduled_operation_ds([bond], set()) == Decimal("0")


@pytest.mark.unit
def test_scheduled_operation_ds_ignores_pure_ir_schedule() -> None:
    """A schedule with only interest_reserve / capitalized_interest phases (no
    PI/IO operation phase) contributes zero — there's no recurring DS."""
    ir_only = _ScheduledCarryModule(
        schedule=[
            {"carry_type": "interest_reserve",
             "duration": {"type": "remainder"}, "rate_pct": 6.0},
        ],
    )

    assert _scheduled_operation_ds([ir_only], {ir_only.id}) == Decimal("0")


@pytest.mark.unit
def test_op_phase_rate_prefers_schedule_pi_over_source() -> None:
    """Regression: when carry.schedule PI rate disagrees with source.interest_rate_pct,
    the sizer must use the schedule rate (the rate cashflow actually pays) so
    sized DSCR matches realised DSCR."""
    carry = {
        "schedule": [
            {"label": "PI", "carry_type": "pi",
             "duration": {"type": "remainder"}, "rate_pct": 5.5},
        ],
    }
    src = {"interest_rate_pct": 6.0, "amort_term_years": 30}
    rate, amort = _op_phase_rate_and_amort(carry, src)
    assert rate == 5.5
    assert amort == 30


@pytest.mark.unit
def test_op_phase_rate_prefers_schedule_io_over_source() -> None:
    """IO-only phase rate also wins over source rate."""
    carry = {
        "schedule": [
            {"carry_type": "io_only", "duration": {"type": "remainder"}, "rate_pct": 4.75},
        ],
    }
    src = {"interest_rate_pct": 6.0}
    rate, _amort = _op_phase_rate_and_amort(carry, src)
    assert rate == 4.75


@pytest.mark.unit
def test_op_phase_rate_skips_ir_ci_phases() -> None:
    """IR/CI phases are pre-funded, not operating DS — they don't supply the rate."""
    carry = {
        "schedule": [
            {"carry_type": "interest_reserve",
             "duration": {"type": "months", "months": 6}, "rate_pct": 4.0},
            {"carry_type": "pi",
             "duration": {"type": "remainder"}, "rate_pct": 5.5,
             "amort_term_years": 25},
        ],
    }
    src = {"interest_rate_pct": 6.0}
    rate, amort = _op_phase_rate_and_amort(carry, src)
    assert rate == 5.5
    assert amort == 25


@pytest.mark.unit
def test_op_phase_rate_falls_back_to_source_when_no_schedule() -> None:
    """Legacy modules without carry.schedule use source.interest_rate_pct."""
    rate, amort = _op_phase_rate_and_amort(
        carry={},
        src={"interest_rate_pct": 6.5, "amort_term_years": 20},
    )
    assert rate == 6.5
    assert amort == 20


@pytest.mark.unit
def test_op_phase_rate_falls_back_to_legacy_phased_carry() -> None:
    """Older deals used carry.phases[name='operation'] — still honored."""
    carry = {"phases": [
        {"name": "construction", "carry_type": "io_only", "io_rate_pct": 7.0},
        {"name": "operation", "carry_type": "pi", "rate_pct": 5.25, "amort_term_years": 28},
    ]}
    rate, amort = _op_phase_rate_and_amort(carry, src={"interest_rate_pct": 6.0})
    assert rate == 5.25
    assert amort == 28


@pytest.mark.unit
def test_op_phase_rate_defaults_amort_to_30() -> None:
    """Missing amort everywhere → 30 year default."""
    _rate, amort = _op_phase_rate_and_amort(carry={}, src={"interest_rate_pct": 6.0})
    assert amort == 30


# ---------------------------------------------------------------------------
# Construction-phase rate resolution (mirrors _op_phase_rate_and_amort)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_constr_phase_rate_prefers_schedule_ir_over_source() -> None:
    """Regression: schedule-format carry with IR phase must supply the
    construction rate. Prior behavior used `_get_phase_carry(carry, "construction")`
    which only matched legacy phased format, falling back to source.interest_rate_pct
    and overstating construction IR on schedule-format loans."""
    carry = {
        "schedule": [
            {"label": "IR", "carry_type": "interest_reserve",
             "duration": {"type": "milestone", "milestone": "operation_stabilized"},
             "rate_pct": 5.5},
            {"label": "PI", "carry_type": "pi",
             "duration": {"type": "remainder"}, "rate_pct": 5.5},
        ],
    }
    src = {"interest_rate_pct": 6.0}
    assert _constr_phase_rate_pct(carry, src) == 5.5


@pytest.mark.unit
def test_constr_phase_rate_prefers_schedule_ci_over_source() -> None:
    """Capitalized-interest phase rate also wins over source rate."""
    carry = {
        "schedule": [
            {"carry_type": "capitalized_interest",
             "duration": {"type": "months", "months": 18}, "rate_pct": 4.75},
        ],
    }
    src = {"interest_rate_pct": 6.0}
    assert _constr_phase_rate_pct(carry, src) == 4.75


@pytest.mark.unit
def test_constr_phase_rate_skips_pi_io_in_schedule() -> None:
    """PI/IO phases are operation-phase carry — don't supply construction rate."""
    carry = {
        "schedule": [
            {"carry_type": "pi",
             "duration": {"type": "remainder"}, "rate_pct": 5.5},
        ],
    }
    src = {"interest_rate_pct": 6.0}
    # No IR/CI phase in schedule → falls back through legacy phases → source rate
    assert _constr_phase_rate_pct(carry, src) == 6.0


@pytest.mark.unit
def test_constr_phase_rate_falls_back_to_legacy_phased_carry() -> None:
    """Older deals used carry.phases[name='construction'] — still honored."""
    carry = {"phases": [
        {"name": "construction", "carry_type": "io_only", "io_rate_pct": 7.0},
        {"name": "operation", "carry_type": "pi", "rate_pct": 5.25},
    ]}
    assert _constr_phase_rate_pct(carry, src={"interest_rate_pct": 6.0}) == 7.0


@pytest.mark.unit
def test_constr_phase_rate_falls_back_to_source_when_no_carry() -> None:
    """Legacy modules without carry → source.interest_rate_pct."""
    assert _constr_phase_rate_pct(carry={}, src={"interest_rate_pct": 6.5}) == 6.5


@pytest.mark.unit
def test_constr_phase_rate_returns_none_when_nothing_set() -> None:
    """No schedule, no phases, no source rate → None."""
    assert _constr_phase_rate_pct(carry={}, src={}) is None


@pytest.mark.unit
def test_schedule_preop_months_uses_months_duration() -> None:
    """User entered 36 months IR — preop_months returns 36."""
    schedule = [
        {"carry_type": "interest_reserve",
         "duration": {"type": "months", "months": 36}, "rate_pct": 6.0},
        {"carry_type": "pi", "duration": {"type": "remainder"}, "rate_pct": 6.0},
    ]
    assert _schedule_preop_months(schedule, {"_total": 360}, 0) == 36


@pytest.mark.unit
def test_schedule_preop_months_uses_milestone_duration() -> None:
    """IR phase ends at milestone — preop_months follows the milestone-month map."""
    schedule = [
        {"carry_type": "interest_reserve",
         "duration": {"type": "milestone", "milestone_key": "stabilization"},
         "rate_pct": 6.0},
        {"carry_type": "pi", "duration": {"type": "remainder"}, "rate_pct": 6.0},
    ]
    # loan starts at absolute month 0; stabilization milestone at month 24
    assert _schedule_preop_months(
        schedule, {"_total": 360, "stabilization": 24}, 0
    ) == 24


@pytest.mark.unit
def test_schedule_preop_months_sums_ir_and_ci_phases() -> None:
    """Multiple pre-funded carry phases (IR + CI) sum together."""
    schedule = [
        {"carry_type": "interest_reserve",
         "duration": {"type": "months", "months": 6}, "rate_pct": 6.0},
        {"carry_type": "capitalized_interest",
         "duration": {"type": "months", "months": 18}, "rate_pct": 6.0},
        {"carry_type": "pi", "duration": {"type": "remainder"}, "rate_pct": 6.0},
    ]
    assert _schedule_preop_months(schedule, {"_total": 360}, 0) == 24


@pytest.mark.unit
def test_schedule_preop_months_ignores_pi_and_io() -> None:
    """PI / IO phases are periodic, not pre-funded — excluded from preop sum."""
    schedule = [
        {"carry_type": "io_only",
         "duration": {"type": "months", "months": 12}, "rate_pct": 6.0},
        {"carry_type": "pi", "duration": {"type": "remainder"}, "rate_pct": 6.0},
    ]
    assert _schedule_preop_months(schedule, {"_total": 360}, 0) == 0


@pytest.mark.unit
def test_schedule_preop_months_empty_schedule() -> None:
    assert _schedule_preop_months([], {"_total": 360}, 0) == 0


@pytest.mark.unit
def test_scheduled_operation_ds_sums_multiple_modules() -> None:
    bond_a = _ScheduledCarryModule(
        schedule=[
            {"carry_type": "pi", "duration": {"type": "remainder"},
             "rate_pct": 6.0, "amort_term_years": 30},
        ],
        amount="1000000",
    )
    bond_b = _ScheduledCarryModule(
        schedule=[
            {"carry_type": "pi", "duration": {"type": "remainder"},
             "rate_pct": 6.0, "amort_term_years": 30},
        ],
        amount="500000",
    )

    ds = _scheduled_operation_ds([bond_a, bond_b], {bond_a.id, bond_b.id})

    # Combined PMT ≈ $8,991 (the same as the $1.5M test above)
    assert ds > Decimal("8900")
    assert ds < Decimal("9100")


# ---------------------------------------------------------------------------
# _ir_lease_up_pool — unit tests
# ---------------------------------------------------------------------------

def _make_lease_up_phase(months: int) -> PhaseSpec:
    return PhaseSpec(period_type=PeriodType.lease_up, months=months)


def _make_inputs_for_ir(
    *,
    initial_occupancy_pct: float = 0.0,
    unit_count_new: int = 10,
    lease_up_curve: str = "linear",
) -> OperationalInputs:
    return OperationalInputs(
        unit_count_new=unit_count_new,
        initial_occupancy_pct=Decimal(str(initial_occupancy_pct)),
        lease_up_curve=lease_up_curve,
    )


def _make_rent_stream(amount_per_unit_monthly: float, unit_count: int = 10) -> IncomeStream:
    return IncomeStream(
        stream_type="residential_rent",
        label="Rent",
        amount_per_unit_monthly=Decimal(str(amount_per_unit_monthly)),
        unit_count=unit_count,
        stabilized_occupancy_pct=Decimal("95"),
        active_in_phases=["lease_up", "stabilized"],
    )


def _make_opex_line(annual_amount: float) -> OperatingExpenseLine:
    return OperatingExpenseLine(
        label="Operating Expenses",
        annual_amount=Decimal(str(annual_amount)),
        active_in_phases=["lease_up", "stabilized"],
    )


@pytest.mark.unit
def test_ir_lease_up_pool_no_streams_returns_full_interest() -> None:
    """With no income streams, every month is a full shortfall."""
    funded = Decimal("1000000")
    rate_pct = Decimal("6")
    n_months = 6
    phase = _make_lease_up_phase(n_months)
    inputs = _make_inputs_for_ir()

    pool = _ir_lease_up_pool(funded, rate_pct, n_months, phase, [], [], inputs)

    # Full interest: 1_000_000 × 6% / 12 × 6 months = 30_000
    assert pool == Decimal("30000.000000")


@pytest.mark.unit
def test_ir_lease_up_pool_income_does_not_offset_sized_interest() -> None:
    """LUR-blind: even a fully-covering income stream cannot shrink IR.

    Pre-spec behavior netted NOI against sized interest and could return 0
    when revenue covered every month. Spec §3.1 forbids that: the lender
    funds the **full** sized interest at Close; ramping rent becomes a
    runtime principal-paydown sweep (Slice 5), not a sizing offset.
    """
    funded = Decimal("500000")
    rate_pct = Decimal("6")
    # Income stream that, pre-spec, would have driven the pool to zero.
    stream = _make_rent_stream(500, unit_count=10)
    inputs = _make_inputs_for_ir(initial_occupancy_pct=50.0)
    phase = _make_lease_up_phase(6)

    pool = _ir_lease_up_pool(funded, rate_pct, 6, phase, [stream], [], inputs)

    # 500_000 × 6% / 12 × 6 = 15_000
    assert pool == Decimal("15000.000000")


@pytest.mark.unit
def test_ir_lease_up_pool_partial_ramp_does_not_alter_pool() -> None:
    """LUR-blind: a slow ramp produces the same IR as no income at all.

    Pre-spec, this test asserted that early-month shortfalls reduced the
    pool below the gross interest figure. Under the spec the pool equals
    gross interest exactly — the lease-up sweep handles whatever NOI does
    show up at runtime.
    """
    funded = Decimal("1200000")
    rate_pct = Decimal("5")
    stream = _make_rent_stream(800, unit_count=10)
    inputs = _make_inputs_for_ir(initial_occupancy_pct=0.0)
    phase = _make_lease_up_phase(12)

    pool = _ir_lease_up_pool(funded, rate_pct, 12, phase, [stream], [], inputs)

    # 1_200_000 × 5% / 12 × 12 = 60_000
    assert pool == Decimal("60000.000000")


@pytest.mark.unit
def test_ir_lease_up_pool_ignores_opex() -> None:
    """LUR-blind: OpEx cannot enlarge the IR pool either.

    Pre-spec, OpEx reduced NOI and therefore enlarged the IR shortfall.
    Under the spec, OpEx falls under ODR (Slice 4); IR stays scoped to
    lender interest only.
    """
    funded = Decimal("1000000")
    rate_pct = Decimal("6")
    stream = _make_rent_stream(500, unit_count=10)
    opex = _make_opex_line(annual_amount=48000)
    inputs = _make_inputs_for_ir(initial_occupancy_pct=50.0)
    phase = _make_lease_up_phase(6)

    pool_with_opex = _ir_lease_up_pool(
        funded, rate_pct, 6, phase, [stream], [opex], inputs
    )
    pool_no_opex = _ir_lease_up_pool(
        funded, rate_pct, 6, phase, [stream], [], inputs
    )

    # Both must equal funded × rate / 12 × months — OpEx & rent are inert.
    expected = Decimal("1000000") * Decimal("6") / Decimal("100") / Decimal("12") * Decimal("6")
    assert pool_with_opex == pool_no_opex
    assert pool_with_opex == expected.quantize(Decimal("0.000001"))


@pytest.mark.unit
def test_ir_lease_up_pool_zero_months_returns_zero() -> None:
    pool = _ir_lease_up_pool(
        Decimal("1000000"), Decimal("6"), 0, _make_lease_up_phase(0), [], [], _make_inputs_for_ir()
    )
    assert pool == Decimal("0")


@pytest.mark.unit
def test_sum_ir_lease_up_interest_no_ir_modules_returns_zero() -> None:
    """Modules without IR carry don't contribute."""
    phases = [
        PhaseSpec(period_type=PeriodType.construction, months=12),
        PhaseSpec(period_type=PeriodType.lease_up, months=6),
    ]
    # IO-only module — not IR
    m = _ScheduledCarryModule(
        schedule=[{"carry_type": "io_only", "duration": {"type": "remainder"}, "rate_pct": 6.0}],
        amount="1000000",
    )
    m.vehicle_type = "debt"
    m.active_phase_start = "construction"
    m.active_phase_end = "stabilized"
    m.exit_terms = {}
    assert _sum_ir_lease_up_interest([m], phases) == Decimal("0")


@pytest.mark.unit
def test_sum_ir_lease_up_interest_uses_schedule_rate_over_source_rate() -> None:
    """Rate lookup precedence: schedule-phase rate beats source headline rate.

    A tax-exempt bond with carry.schedule rate_pct=5.5 and
    source.interest_rate_pct=6.0 (the legacy headline rate) must size IR
    using 5.5%, matching what the cashflow engine actually charges during
    the IR phase. Source-first precedence would over-estimate IR by ~9%.
    """
    phases = [
        PhaseSpec(period_type=PeriodType.construction, months=12),
        PhaseSpec(period_type=PeriodType.lease_up, months=6),
    ]
    m = _ScheduledCarryModule(
        schedule=[
            {"label": "IR", "carry_type": "interest_reserve",
             "duration": {"type": "milestone",
                          "milestone_key": "operation_stabilized"},
             "rate_pct": 5.5},
            {"label": "PI", "carry_type": "pi",
             "duration": {"type": "remainder"}, "rate_pct": 5.5},
        ],
        amount="10000000",
        rate_pct=6.0,  # Headline source rate — must NOT win
    )
    m.vehicle_type = "debt"
    m.active_phase_start = "construction"
    m.active_phase_end = "stabilized"
    m.exit_terms = {}

    out = _sum_ir_lease_up_interest([m], phases)
    expected = (Decimal("10000000") * Decimal("5.5") / Decimal("100")
                / Decimal("12"))
    assert abs(out - expected) < Decimal("0.01"), (
        f"Schedule rate 5.5% must win over source 6.0%, got {out} "
        f"vs expected {expected}"
    )
    # Verify the bug-direction: source-first would have given ~9% more.
    bug_value = (Decimal("10000000") * Decimal("6.0") / Decimal("100")
                 / Decimal("12"))
    assert out < bug_value


@pytest.mark.unit
def test_compute_preop_carry_cost_ci_uses_compound_interest() -> None:
    """CI pre-sizing in _compute_preop_carry_cost must use compound formula.

    Simple interest: funded * r/1200 * n
    Compound:        funded * ((1 + r/1200)^n - 1)

    For r=8%, n=12: simple=$80,000 vs compound≈$83,000.
    The result must match compound, not simple.
    """
    funded = Decimal("1000000")
    rate = Decimal("8")
    n = 12
    schedule = [
        {"carry_type": "capitalized_interest",
         "duration": {"type": "months", "months": n}, "rate_pct": float(rate)},
        {"carry_type": "pi", "duration": {"type": "remainder"}, "rate_pct": 8.0},
    ]

    result = _compute_preop_carry_cost(
        schedule=schedule,
        funded=funded,
        preop_months=n,
        base_rate=rate,
        milestone_month_map={"_total": 360},
        loan_start_abs=0,
    )

    monthly_rate = rate / Decimal("1200")
    compound_expected = funded * ((Decimal("1") + monthly_rate) ** n - Decimal("1"))
    simple_wrong = funded * monthly_rate * Decimal(str(n))

    assert abs(result - compound_expected) < Decimal("1.00"), (
        f"Expected compound {compound_expected:.2f}, got {result:.2f}"
    )
    assert abs(result - simple_wrong) > Decimal("100"), (
        f"Result {result:.2f} matches simple interest — compound fix not applied"
    )
