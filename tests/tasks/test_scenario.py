from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vicinitideals.models.base import Base
from vicinitideals.models.cashflow import CashFlow, OperationalOutputs
from vicinitideals.models.deal import Deal, DealModel, DealOpportunity, OperationalInputs, ProjectType
from vicinitideals.models.manifest import WorkflowRunManifest
from vicinitideals.models.org import Organization, User
from vicinitideals.models.project import (
    Opportunity,
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
    Project,
    ProjectCategory,
    ProjectSource,
    ProjectStatus,
)
from vicinitideals.models.scenario import Scenario, ScenarioResult, ScenarioStatus
from vicinitideals.tasks.scenario import run_scenario


@pytest.fixture
async def test_session_factory(tmp_path):
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'stage1e_scenario.db'}",
        future=True,
    )
    session_factory = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list,
                    [
                        Organization.__table__,
                        User.__table__,
                        Opportunity.__table__,
                        Deal.__table__,
                        DealOpportunity.__table__,
                        Project.__table__,
                        DealModel.__table__,
                        OperationalInputs.__table__,
                        CashFlow.__table__,
                        OperationalOutputs.__table__,
                        WorkflowRunManifest.__table__,
                        Scenario.__table__,
                        ScenarioResult.__table__,
                    ],
                ),
            )
        )

    try:
        yield session_factory
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_run_scenario_writes_one_result_per_step(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    observed_values: list[Decimal] = []
    caplog.set_level(logging.INFO, logger="vicinitideals.tasks.scenario")

    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.AsyncSessionLocal",
        test_session_factory,
    )

    async def fake_compute_cash_flows(deal_model_id, session):  # type: ignore[no-untyped-def]
        inputs = (
            await session.execute(
                select(OperationalInputs)
                .join(Project, Project.id == OperationalInputs.project_id)
                .where(Project.scenario_id == deal_model_id)
            )
        ).scalar_one()
        observed_values.append(Decimal(str(inputs.exit_cap_rate_pct)))
        return {
            "project_irr_levered": Decimal("14.500000"),
            "total_project_cost": Decimal("1500000.000000"),
            "equity_required": Decimal("500000.000000"),
            "noi_stabilized": Decimal("60000.000000"),
        }

    async def fake_compute_waterfall(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "lp_irr_pct": Decimal("12.250000"),
            "gp_irr_pct": Decimal("16.750000"),
        }

    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.compute_waterfall",
        fake_compute_waterfall,
    )

    scenario_id = await _seed_scenario(test_session_factory)

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Scenario, scenario_id)
        results = list(
            (
                await session.execute(
                    select(ScenarioResult)
                    .where(ScenarioResult.sensitivity_id == scenario_id)
                    .order_by(ScenarioResult.variable_value.asc())
                )
            ).scalars()
        )

    assert scenario is not None
    assert scenario.status == ScenarioStatus.complete
    assert len(results) == 4
    assert observed_values == [
        Decimal("4.500000"),
        Decimal("5.000000"),
        Decimal("5.500000"),
        Decimal("6.000000"),
    ]

    assert scenario.model_version_snapshot is not None
    snapshot = scenario.model_version_snapshot
    assert snapshot["deal_model_id"] == str(scenario.scenario_id)
    assert snapshot["deal_model_version"] == 1
    assert snapshot["project_type"] == ProjectType.new_construction.value
    assert snapshot["unit_count_new"] == 12
    assert snapshot["purchase_price"] == "1250000.000000"
    assert snapshot["exit_cap_rate_pct"] == "5.500000"
    assert snapshot["hold_period_years"] == "5.000000"
    captured_at = snapshot.get("captured_at")
    assert isinstance(captured_at, str)
    assert datetime.fromisoformat(captured_at)

    first = results[0]
    assert Decimal(str(first.project_irr_pct)) == Decimal("14.500000")
    assert Decimal(str(first.lp_irr_pct)) == Decimal("12.250000")
    assert Decimal(str(first.gp_irr_pct)) == Decimal("16.750000")
    assert Decimal(str(first.equity_multiple)) == Decimal("3.000000")
    assert Decimal(str(first.cash_on_cash_year1_pct)) == Decimal("12.000000")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "scenario_run_started" in messages
    assert "scenario_run_completed" in messages


@pytest.mark.asyncio
async def test_run_scenario_preserves_prior_results_with_incremented_run_number(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
) -> None:
    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.AsyncSessionLocal",
        test_session_factory,
    )

    async def fake_compute_cash_flows(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "project_irr_levered": Decimal("14.500000"),
            "total_project_cost": Decimal("1500000.000000"),
            "equity_required": Decimal("500000.000000"),
            "noi_stabilized": Decimal("60000.000000"),
        }

    async def fake_compute_waterfall(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "lp_irr_pct": Decimal("12.250000"),
            "gp_irr_pct": Decimal("16.750000"),
        }

    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )
    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.compute_waterfall",
        fake_compute_waterfall,
    )

    scenario_id = await _seed_scenario(test_session_factory)

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Scenario, scenario_id)
        assert scenario is not None
        assert scenario.run_count == 1
        first_run_results = list(
            (
                await session.execute(
                    select(ScenarioResult)
                    .where(ScenarioResult.sensitivity_id == scenario_id)
                    .order_by(ScenarioResult.run_number.asc(), ScenarioResult.variable_value.asc())
                )
            ).scalars()
        )
        assert len(first_run_results) == 4
        assert {result.run_number for result in first_run_results} == {1}

        scenario.range_min = Decimal("5.000000")
        scenario.range_max = Decimal("6.500000")
        scenario.range_steps = 4
        await session.commit()

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Scenario, scenario_id)
        results = list(
            (
                await session.execute(
                    select(ScenarioResult)
                    .where(ScenarioResult.sensitivity_id == scenario_id)
                    .order_by(ScenarioResult.run_number.asc(), ScenarioResult.variable_value.asc())
                )
            ).scalars()
        )

    assert scenario is not None
    assert scenario.run_count == 2
    assert len(results) == 8

    run_one = [result for result in results if result.run_number == 1]
    run_two = [result for result in results if result.run_number == 2]
    assert [Decimal(str(result.variable_value)) for result in run_one] == [
        Decimal("4.500000"),
        Decimal("5.000000"),
        Decimal("5.500000"),
        Decimal("6.000000"),
    ]
    assert [Decimal(str(result.variable_value)) for result in run_two] == [
        Decimal("5.000000"),
        Decimal("5.500000"),
        Decimal("6.000000"),
        Decimal("6.500000"),
    ]


@pytest.mark.asyncio
async def test_run_scenario_marks_invalid_variable_failed(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
) -> None:
    calls = 0

    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.AsyncSessionLocal",
        test_session_factory,
    )

    async def fake_compute_cash_flows(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(
        "vicinitideals.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )

    scenario_id = await _seed_scenario(
        test_session_factory,
        variable="operational.not_a_real_key",
    )

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Scenario, scenario_id)
        results = list(
            (
                await session.execute(
                    select(ScenarioResult).where(ScenarioResult.sensitivity_id == scenario_id)
                )
            ).scalars()
        )

    assert scenario is not None
    assert scenario.status == ScenarioStatus.failed
    assert calls == 0
    assert results == []


async def _seed_scenario(test_session_factory, variable: str = "operational.exit_cap_rate_pct"):
    async with test_session_factory() as session:
        org = Organization(id=uuid4(), name="Scenario Org", slug=f"scenario-{uuid4().hex[:8]}")
        user = User(id=uuid4(), org_id=org.id, name="Scenario User", display_color="#00AAFF")
        opportunity = Opportunity(
            id=uuid4(),
            org_id=org.id,
            name="Scenario Opportunity",
            status=OpportunityStatus.active,
            project_category=OpportunityCategory.proposed,
            source=OpportunitySource.manual,
            created_by_user_id=user.id,
        )
        top_deal = Deal(
            id=uuid4(),
            org_id=org.id,
            name="Scenario Deal",
            created_by_user_id=user.id,
        )
        deal_opp = DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id)
        deal = DealModel(
            id=uuid4(),
            deal_id=top_deal.id,
            created_by_user_id=user.id,
            name="Scenario Base Case",
            version=1,
            is_active=True,
            project_type=ProjectType.new_construction,
        )
        dev_project = Project(
            id=uuid4(),
            scenario_id=deal.id,
            opportunity_id=opportunity.id,
            name="Scenario Project",
            deal_type=ProjectType.new_construction.value,
        )
        inputs = OperationalInputs(
            project_id=dev_project.id,
            unit_count_existing=4,
            unit_count_new=12,
            purchase_price=Decimal("1250000.000000"),
            exit_cap_rate_pct=Decimal("5.500000"),
            lease_up_months=6,
            expense_growth_rate_pct_annual=Decimal("3.000000"),
            hold_period_years=Decimal("5.000000"),
            hard_cost_per_unit=Decimal("180000.000000"),
            opex_per_unit_annual=Decimal("4800.000000"),
            mgmt_fee_pct=Decimal("4.000000"),
            property_tax_annual=Decimal("18000.000000"),
            insurance_annual=Decimal("7200.000000"),
            capex_reserve_per_unit_annual=Decimal("300.000000"),
            selling_costs_pct=Decimal("2.500000"),
        )
        sensitivity = Scenario(
            id=uuid4(),
            opportunity_id=opportunity.id,
            scenario_id=deal.id,
            created_by_user_id=user.id,
            variable=variable,
            range_min=Decimal("4.500000"),
            range_max=Decimal("6.000000"),
            range_steps=4,
            status=ScenarioStatus.pending,
        )

        session.add_all([org, user, opportunity, top_deal, deal_opp, deal, dev_project, inputs, sensitivity])
        await session.commit()
        return sensitivity.id
