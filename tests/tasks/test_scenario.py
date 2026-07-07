from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.deal import OperationalInputs, ProjectType
from app.models.project import Project
from app.models.scenario import Sensitivity, SensitivityResult, SensitivityStatus
from app.tasks.scenario import run_scenario
from tests.conftest import seed_deal_model, seed_opportunity, seed_org


@pytest_asyncio.fixture(loop_scope="session")
async def test_session_factory(_test_engine, session):
    """Session factory bound to the per-run Postgres test DB.

    run_scenario opens its own sessions via app.db.AsyncSessionLocal, which
    the autouse `_rebind_app_db` conftest fixture already points at the same
    engine — no monkeypatching needed. Depending on the `session` fixture
    ensures the conftest TRUNCATE-on-teardown cleans up rows committed here.
    """
    yield async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.mark.asyncio
async def test_run_scenario_writes_one_result_per_step(
    monkeypatch: pytest.MonkeyPatch,
    test_session_factory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    observed_values: list[Decimal] = []
    caplog.set_level(logging.INFO, logger="app.tasks.scenario")

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
        "app.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )
    monkeypatch.setattr(
        "app.tasks.scenario.compute_waterfall",
        fake_compute_waterfall,
    )

    scenario_id = await _seed_scenario(test_session_factory)

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Sensitivity, scenario_id)
        results = list(
            (
                await session.execute(
                    select(SensitivityResult)
                    .where(SensitivityResult.sensitivity_id == scenario_id)
                    .order_by(SensitivityResult.variable_value.asc())
                )
            ).scalars()
        )

    assert scenario is not None
    assert scenario.status == SensitivityStatus.complete
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
        "app.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )
    monkeypatch.setattr(
        "app.tasks.scenario.compute_waterfall",
        fake_compute_waterfall,
    )

    scenario_id = await _seed_scenario(test_session_factory)

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Sensitivity, scenario_id)
        assert scenario is not None
        assert scenario.run_count == 1
        first_run_results = list(
            (
                await session.execute(
                    select(SensitivityResult)
                    .where(SensitivityResult.sensitivity_id == scenario_id)
                    .order_by(SensitivityResult.run_number.asc(), SensitivityResult.variable_value.asc())
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
        scenario = await session.get(Sensitivity, scenario_id)
        results = list(
            (
                await session.execute(
                    select(SensitivityResult)
                    .where(SensitivityResult.sensitivity_id == scenario_id)
                    .order_by(SensitivityResult.run_number.asc(), SensitivityResult.variable_value.asc())
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

    async def fake_compute_cash_flows(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(
        "app.tasks.scenario.compute_cash_flows",
        fake_compute_cash_flows,
    )

    scenario_id = await _seed_scenario(
        test_session_factory,
        variable="operational.not_a_real_key",
    )

    await asyncio.to_thread(cast(Any, run_scenario), str(scenario_id))

    async with test_session_factory() as session:
        scenario = await session.get(Sensitivity, scenario_id)
        results = list(
            (
                await session.execute(
                    select(SensitivityResult).where(SensitivityResult.sensitivity_id == scenario_id)
                )
            ).scalars()
        )

    assert scenario is not None
    assert scenario.status == SensitivityStatus.failed
    assert calls == 0
    assert results == []


async def _seed_scenario(test_session_factory, variable: str = "operational.exit_cap_rate_pct"):
    async with test_session_factory() as session:
        org, user = await seed_org(session)
        opportunity = await seed_opportunity(session, org, user, name="Scenario Opportunity")
        deal_model = await seed_deal_model(
            session,
            opportunity,
            user,
            name="Scenario Base Case",
            project_type=ProjectType.new_construction,
        )
        dev_project = Project(
            id=uuid4(),
            scenario_id=deal_model.id,
            opportunity_id=opportunity.id,
            name="Scenario Project",
        )
        session.add(dev_project)
        await session.flush()

        inputs = OperationalInputs(
            project_id=dev_project.id,
            unit_count_existing=4,
            unit_count_new=12,
            purchase_price=Decimal("1250000.000000"),
            exit_cap_rate_pct=Decimal("5.500000"),
            lease_up_months=6,
            expense_growth_rate_pct_annual=Decimal("3.000000"),
            hard_cost_per_unit=Decimal("180000.000000"),
            opex_per_unit_annual=Decimal("4800.000000"),
            mgmt_fee_pct=Decimal("4.000000"),
            property_tax_annual=Decimal("18000.000000"),
            insurance_annual=Decimal("7200.000000"),
            capex_reserve_per_unit_annual=Decimal("300.000000"),
            selling_costs_pct=Decimal("2.500000"),
        )
        sensitivity = Sensitivity(
            id=uuid4(),
            opportunity_id=opportunity.id,
            scenario_id=deal_model.id,
            created_by_user_id=user.id,
            variable=variable,
            range_min=Decimal("4.500000"),
            range_max=Decimal("6.000000"),
            range_steps=4,
            status=SensitivityStatus.pending,
        )

        session.add_all([inputs, sensitivity])
        await session.commit()
        return sensitivity.id
