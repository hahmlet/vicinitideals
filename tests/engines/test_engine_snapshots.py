"""Engine snapshot tests — safety net for the cashflow.py compile/evaluate refactor.

The compile/evaluate refactor must not change observable engine output for any
existing scenario. Each scenario in this file seeds a deterministic deal,
runs ``compute_cash_flows``, serializes the persisted engine state to JSON, and
asserts byte-equivalence against a checked-in snapshot under
``tests/engines/snapshots/``.

To accept new output (when intentionally changing engine math):

    SNAPSHOT_UPDATE=1 uv run pytest tests/engines/test_engine_snapshots.py -q

Coverage grows alongside the refactor — start scenarios are minimal; PR1 and PR2
add capitalized-interest, multi-project, DSCR-bound, and LTV-bound cases.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.engines.cashflow import compute_cash_flows
from app.models import Base
from app.models.capital import CapitalModule, FunderType
from app.models.deal import (
    Deal,
    DealModel,
    DealOpportunity,
    IncomeStream,
    OperatingExpenseLine,
    OperationalInputs,
    ProjectType,
    UseLine,
    UseLinePhase,
)
from app.models.org import Organization, User
from app.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
    Project,
)
from tests.engines.snapshot_helpers import (
    assert_matches_snapshot,
    serialize_engine_state,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Independent in-memory engine per test — keeps snapshots reproducible."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Scenario seeds
# ---------------------------------------------------------------------------


async def seed_minimal_value_add(session: AsyncSession) -> UUID:
    """A deterministic 12-unit value-add reno without debt or use lines.

    Same shape as the existing `_seed_cashflow_deal` in test_cashflow.py —
    a low-risk smoke baseline. UUIDs are auto-generated; the snapshot
    serializer strips raw UUIDs and uses stable ordinals (project_idx,
    period, label) so output is reproducible across runs.
    """
    org = Organization(id=uuid4(), name="Snapshot Org", slug=f"snapshot-org-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Snapshot User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name="619 NE 190th Ave, 12-unit reno",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    top_deal = Deal(
        id=uuid4(),
        org_id=org.id,
        name="Snapshot — Minimal Value-Add",
        created_by_user_id=user.id,
    )
    scenario = DealModel(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Snapshot — Minimal Value-Add",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add_all([org, user, opportunity, top_deal, scenario])
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    project = Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="12-unit Major Reno",
        deal_type=ProjectType.value_add.value,
    )
    session.add(project)
    await session.flush()

    session.add_all(
        [
            OperationalInputs(
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
            ),
            IncomeStream(
                project_id=project.id,
                stream_type="residential_rent",
                label="12 Residential Units",
                unit_count=12,
                amount_per_unit_monthly=Decimal("1450.000000"),
                stabilized_occupancy_pct=Decimal("95.000000"),
                escalation_rate_pct_annual=Decimal("3.000000"),
                active_in_phases=[
                    "hold",
                    "major_renovation",
                    "lease_up",
                    "stabilized",
                    "exit",
                ],
            ),
            IncomeStream(
                project_id=project.id,
                stream_type="laundry",
                label="Laundry",
                amount_fixed_monthly=Decimal("250.000000"),
                stabilized_occupancy_pct=Decimal("100.000000"),
                escalation_rate_pct_annual=Decimal("2.000000"),
                active_in_phases=["hold", "lease_up", "stabilized", "exit"],
            ),
        ]
    )
    await session.flush()
    return scenario.id


async def seed_value_add_with_perm_debt_io(session: AsyncSession) -> UUID:
    """A 12-unit value-add reno with auto-sized permanent debt (IO carry).

    Stack:
      - Permanent Debt (auto), 65% LTV cap, 6% rate, 30yr amort, IO carry
      - Owner Equity, gap-fill

    Uses:
      - Purchase Price (1.8M) — acquisition phase
      - Closing Costs (36k = 2%) — acquisition phase
      - Renovation (360k) — renovation phase

    Auto-sizer coverage: this scenario does fire ``_auto_size_debt_modules``
    end-to-end. The perm debt's ``exit_terms.vehicle="sale"`` is required —
    without it, ``_resolve_vehicle``'s default-selection picks Owner Equity
    (covers same window) as the retirer, which filters perm debt out of the
    gap-fill pool. Real prod scenarios always set vehicle explicitly.

    To trace auto-sizer decisions while debugging seed configurations:

        VD_DIAG_AUTOSIZE=1 uv run pytest tests/engines/test_engine_snapshots.py \\
            -k perm_debt_io -q -s 2>&1 | grep VD_DIAG
    """
    org = Organization(id=uuid4(), name="Snapshot Org Debt", slug=f"snap-debt-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Snapshot User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name="421 SE Stark, 12-unit reno (debt)",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    top_deal = Deal(
        id=uuid4(),
        org_id=org.id,
        name="Snapshot — Value-Add with Perm Debt IO",
        created_by_user_id=user.id,
    )
    scenario = DealModel(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Snapshot — Value-Add with Perm Debt IO",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add_all([org, user, opportunity, top_deal, scenario])
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    project = Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="12-unit Major Reno",
        deal_type=ProjectType.value_add.value,
    )
    session.add(project)
    await session.flush()

    session.add_all(
        [
            OperationalInputs(
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
                dscr_minimum=Decimal("1.150000"),
                debt_types=["permanent_debt"],
                debt_sizing_mode="gap_fill",
            ),
            IncomeStream(
                project_id=project.id,
                stream_type="residential_rent",
                label="12 Residential Units",
                unit_count=12,
                amount_per_unit_monthly=Decimal("1450.000000"),
                stabilized_occupancy_pct=Decimal("95.000000"),
                escalation_rate_pct_annual=Decimal("3.000000"),
                active_in_phases=[
                    "hold",
                    "major_renovation",
                    "lease_up",
                    "stabilized",
                    "exit",
                ],
            ),
            UseLine(
                project_id=project.id,
                label="Purchase Price",
                phase=UseLinePhase.acquisition,
                amount=Decimal("1800000.000000"),
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Closing Costs",
                phase=UseLinePhase.acquisition,
                amount=Decimal("36000.000000"),
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Renovation Hard Costs",
                phase=UseLinePhase.renovation,
                amount=Decimal("360000.000000"),
                timing_type="first_day",
            ),
            CapitalModule(
                scenario_id=scenario.id,
                label="Permanent Debt (auto)",
                funder_type=FunderType.permanent_debt,
                stack_position=1,
                source={
                    "auto_size": True,
                    "interest_rate_pct": 6.0,
                    "ltv_pct": 65.0,
                    "amort_term_years": 30,
                    "refi_cap_rate_pct": 5.75,
                },
                carry={"carry_type": "io_only", "payment_frequency": "monthly"},
                # vehicle="sale" — paid off at divestment, not retired by another
                # module. Without this, _resolve_vehicle's default-selection logic
                # picks Owner Equity (covers same window) as the retirer, which
                # filters perm debt out of auto_modules in _auto_size_debt_modules.
                exit_terms={"vehicle": "sale", "exit_type": "full_payoff", "trigger": "sale"},
                active_phase_start="acquisition",
                active_phase_end="exit",
            ),
            CapitalModule(
                scenario_id=scenario.id,
                label="Owner Equity",
                funder_type=FunderType.common_equity,
                stack_position=2,
                source={"amount": 0},
                carry={"carry_type": "none", "payment_frequency": "at_exit"},
                exit_terms={"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
                active_phase_start="acquisition",
                active_phase_end="exit",
            ),
        ]
    )
    await session.flush()
    return scenario.id


async def seed_new_construction_with_ci_and_retirement(session: AsyncSession) -> UUID:
    """A new-construction deal with capitalized-interest construction loan
    retired by permanent debt at lease-up start.

    Stack:
      - Construction Loan (auto), 6.5% rate, capitalized_interest carry,
        active acquisition→lease_up, vehicle=<perm debt UUID>
      - Permanent Debt (auto), 6.0% rate, IO carry, 65% LTV, 30yr amort,
        active lease_up→exit, vehicle="sale"
      - Owner Equity, gap-fill, perpetuity

    Uses:
      - Land (1.5M) — acquisition
      - Hard Costs (3.2M) — construction
      - Soft Costs (640k) — pre_construction

    Exercises:
      - Capitalized-interest carry math (full-balance N formula)
      - Retirement chain (construction loan → permanent debt at lease_up)
      - construction_retirement field population in source JSONB
      - Multiple auto-sized modules in a single deal
      - Gap-fill principal solve with closing-cost divisor fold-in
    """
    org = Organization(id=uuid4(), name="Snapshot Org NC", slug=f"snap-nc-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Snapshot User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name="2200 NE Burnside, ground-up 24-unit",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    top_deal = Deal(
        id=uuid4(),
        org_id=org.id,
        name="Snapshot — New Construction (CI Carry + Retirement)",
        created_by_user_id=user.id,
    )
    scenario = DealModel(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Snapshot — New Construction (CI Carry + Retirement)",
        version=1,
        is_active=True,
        project_type=ProjectType.new_construction,
    )
    session.add_all([org, user, opportunity, top_deal, scenario])
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    project = Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="Burnside 24",
        deal_type=ProjectType.new_construction.value,
    )
    session.add(project)
    await session.flush()

    # Pre-allocate UUIDs so we can wire the retirement chain in exit_terms.
    construction_loan_id = uuid4()
    perm_debt_id = uuid4()

    session.add_all(
        [
            OperationalInputs(
                project_id=project.id,
                unit_count_new=24,
                purchase_price=Decimal("1500000"),
                closing_costs_pct=Decimal("2.000000"),
                hold_phase_enabled=False,
                entitlement_months=4,
                construction_months=14,
                lease_up_months=6,
                initial_occupancy_pct=Decimal("0.000000"),
                opex_per_unit_annual=Decimal("4200.000000"),
                expense_growth_rate_pct_annual=Decimal("3.000000"),
                mgmt_fee_pct=Decimal("4.000000"),
                property_tax_annual=Decimal("36000.000000"),
                insurance_annual=Decimal("14400.000000"),
                capex_reserve_per_unit_annual=Decimal("300.000000"),
                hold_period_years=Decimal("3.000000"),
                exit_cap_rate_pct=Decimal("5.500000"),
                selling_costs_pct=Decimal("2.500000"),
                dscr_minimum=Decimal("1.150000"),
                debt_types=["construction_loan", "permanent_debt"],
                debt_sizing_mode="gap_fill",
            ),
            IncomeStream(
                project_id=project.id,
                stream_type="residential_rent",
                label="24 Residential Units",
                unit_count=24,
                amount_per_unit_monthly=Decimal("2100.000000"),
                stabilized_occupancy_pct=Decimal("95.000000"),
                escalation_rate_pct_annual=Decimal("3.000000"),
                active_in_phases=["lease_up", "stabilized", "exit"],
            ),
            UseLine(
                project_id=project.id,
                label="Land",
                phase=UseLinePhase.acquisition,
                amount=Decimal("1500000.000000"),
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Soft Costs",
                phase=UseLinePhase.pre_construction,
                amount=Decimal("640000.000000"),
                timing_type="first_day",
            ),
            UseLine(
                project_id=project.id,
                label="Hard Costs",
                phase=UseLinePhase.construction,
                amount=Decimal("3200000.000000"),
                timing_type="first_day",
            ),
            CapitalModule(
                id=construction_loan_id,
                scenario_id=scenario.id,
                label="Construction Loan (auto)",
                funder_type=FunderType.construction_loan,
                stack_position=1,
                source={
                    "auto_size": True,
                    "interest_rate_pct": 6.5,
                    "ltv_pct": 70.0,
                },
                carry={"carry_type": "capitalized_interest", "payment_frequency": "at_exit"},
                # Retired by the permanent debt module at lease_up start.
                exit_terms={"vehicle": str(perm_debt_id), "exit_type": "refi", "trigger": "stabilization"},
                active_phase_start="acquisition",
                active_phase_end="lease_up",
            ),
            CapitalModule(
                id=perm_debt_id,
                scenario_id=scenario.id,
                label="Permanent Debt (auto)",
                funder_type=FunderType.permanent_debt,
                stack_position=2,
                source={
                    "auto_size": True,
                    "interest_rate_pct": 6.0,
                    "ltv_pct": 65.0,
                    "amort_term_years": 30,
                    "refi_cap_rate_pct": 5.50,
                },
                carry={"carry_type": "io_only", "payment_frequency": "monthly"},
                exit_terms={"vehicle": "sale", "exit_type": "full_payoff", "trigger": "sale"},
                active_phase_start="lease_up",
                active_phase_end="exit",
            ),
            CapitalModule(
                scenario_id=scenario.id,
                label="Owner Equity",
                funder_type=FunderType.common_equity,
                stack_position=3,
                source={"amount": 0},
                carry={"carry_type": "none", "payment_frequency": "at_exit"},
                exit_terms={"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
                active_phase_start="acquisition",
                active_phase_end="exit",
            ),
        ]
    )
    await session.flush()
    return scenario.id


async def _seed_multi_project_value_add_FLAKY_DO_NOT_USE(session: AsyncSession) -> UUID:
    """A multi-project deal with 2 value-add reno projects under one scenario.

    DROPPED FROM HARNESS — flaky output. Diff investigation showed project_idx=1's
    line items intermittently missing from the persisted CashFlowLineItem table
    (3/10 runs miss them entirely). Likely cause: per-project purge in
    _compute_project_cashflow interacting with ORM session state across the
    multi-project iteration loop, possibly because both projects insert in the
    same flush and prev_outputs read race-conditions with subsequent writes.

    Setting distinct created_at timestamps on the two projects did NOT fix it
    (output remained 3/5 flaky), suggesting the issue is in compute order or
    session caching, not project sort. This is a pre-existing engine
    nondeterminism worth investigating separately before adding multi-project
    coverage to the harness.

    Mirrors the shape of session S246's multi-project deal (1203 E Powell +
    East 25). Function kept here for future re-enablement once the engine
    flakiness is resolved.
    """
    org = Organization(id=uuid4(), name="Snapshot Org MP", slug=f"snap-mp-{uuid4().hex[:8]}")
    user = User(id=uuid4(), org_id=org.id, name="Snapshot User", display_color="#3366FF")
    opportunity = Opportunity(
        id=uuid4(),
        org_id=org.id,
        name="Multi-Project: 1203 E Powell + East 25 (synthetic)",
        status=OpportunityStatus.active,
        project_category=OpportunityCategory.proposed,
        source=OpportunitySource.manual,
        created_by_user_id=user.id,
    )
    top_deal = Deal(
        id=uuid4(),
        org_id=org.id,
        name="Snapshot — Multi-Project Value-Add",
        created_by_user_id=user.id,
    )
    scenario = DealModel(
        id=uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Snapshot — Multi-Project Value-Add",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add_all([org, user, opportunity, top_deal, scenario])
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    # Two projects under one scenario. Engine sorts by created_at only, so
    # we set explicit distinct timestamps to make the compute order
    # deterministic (otherwise both get func.now() and tie-breaking is
    # implementation-defined).
    from datetime import datetime, timezone
    t0 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 9, 0, 1, tzinfo=timezone.utc)
    project_powell = Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="1203 E Powell",
        deal_type=ProjectType.value_add.value,
        created_at=t0,
    )
    project_east25 = Project(
        id=uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="East 25",
        deal_type=ProjectType.value_add.value,
        created_at=t1,
    )
    session.add_all([project_powell, project_east25])
    await session.flush()

    # Project 1: 1203 E Powell — 8-unit small value-add
    session.add_all(
        [
            OperationalInputs(
                project_id=project_powell.id,
                unit_count_existing=8,
                unit_count_new=8,
                purchase_price=Decimal("1200000"),
                closing_costs_pct=Decimal("2.000000"),
                hold_phase_enabled=True,
                hold_months=2,
                hold_vacancy_rate_pct=Decimal("8.000000"),
                renovation_cost_total=Decimal("240000"),
                renovation_months=4,
                lease_up_months=3,
                initial_occupancy_pct=Decimal("60.000000"),
                opex_per_unit_annual=Decimal("4500.000000"),
                expense_growth_rate_pct_annual=Decimal("3.000000"),
                mgmt_fee_pct=Decimal("4.000000"),
                property_tax_annual=Decimal("12000.000000"),
                insurance_annual=Decimal("4800.000000"),
                capex_reserve_per_unit_annual=Decimal("300.000000"),
                hold_period_years=Decimal("2.000000"),
                exit_cap_rate_pct=Decimal("5.750000"),
                selling_costs_pct=Decimal("2.500000"),
                income_reduction_pct_during_reno=Decimal("35.000000"),
            ),
            IncomeStream(
                project_id=project_powell.id,
                stream_type="residential_rent",
                label="Powell — 8 Residential Units",
                unit_count=8,
                amount_per_unit_monthly=Decimal("1500.000000"),
                stabilized_occupancy_pct=Decimal("95.000000"),
                escalation_rate_pct_annual=Decimal("3.000000"),
                active_in_phases=["hold", "major_renovation", "lease_up", "stabilized", "exit"],
            ),
        ]
    )

    # Project 2: East 25 — 12-unit larger value-add
    session.add_all(
        [
            OperationalInputs(
                project_id=project_east25.id,
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
            ),
            IncomeStream(
                project_id=project_east25.id,
                stream_type="residential_rent",
                label="East 25 — 12 Residential Units",
                unit_count=12,
                amount_per_unit_monthly=Decimal("1450.000000"),
                stabilized_occupancy_pct=Decimal("95.000000"),
                escalation_rate_pct_annual=Decimal("3.000000"),
                active_in_phases=["hold", "major_renovation", "lease_up", "stabilized", "exit"],
            ),
        ]
    )
    await session.flush()
    return scenario.id


# Add scenarios here as PR1/PR2 progress. Each entry:
#   (snapshot_name, seed_function)
# The seed function must return the scenario UUID. UUIDs are auto-generated
# (except where retirement chains require pre-allocation); the snapshot
# serializer strips raw UUIDs and uses stable ordinals (project_idx, period,
# label) so output is byte-reproducible across runs.
SCENARIOS: list[tuple[str, Callable[[AsyncSession], Awaitable[UUID]]]] = [
    ("minimal_value_add", seed_minimal_value_add),
    ("value_add_with_perm_debt_io", seed_value_add_with_perm_debt_io),
    ("new_construction_with_ci_and_retirement", seed_new_construction_with_ci_and_retirement),
    # NOTE: multi_project_value_add removed — flaky engine output
    # (see _seed_multi_project_value_add_FLAKY_DO_NOT_USE for the seed and
    # investigation notes). Multi-project coverage lives in the prod
    # baselines (tests/phase2_baseline/) until the engine nondeterminism
    # is investigated.
]


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_name,seed_func", SCENARIOS, ids=[s[0] for s in SCENARIOS])
async def test_engine_snapshot(
    db_session: AsyncSession,
    snapshot_name: str,
    seed_func: Callable[[AsyncSession], Awaitable[UUID]],
) -> None:
    scenario_id = await seed_func(db_session)
    await db_session.commit()

    await compute_cash_flows(deal_model_id=scenario_id, session=db_session)
    await db_session.commit()

    actual = await serialize_engine_state(db_session, scenario_id)
    assert_matches_snapshot(actual, snapshot_name)
