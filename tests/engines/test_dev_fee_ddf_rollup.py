"""Deferred Developer Fee (DDF) rollup sizing — multi-project.

Regression coverage for the bug where a `deferred_developer_fee` module was
created project-specific (a single junction to the primary project), so in a
multi-project rollup `_auto_size_ddf_module` only ever filled the primary
project's Sources = Uses gap and every other project's deferred fee silently
dropped to $0 — the DDF opening balance the waterfall reads (`module.source
["amount"]`) came out far too low (usually zero).

These tests exercise the exact sizing functions the per-project compute loop
runs (`_per_project_capital_modules` → `_auto_size_ddf_module` →
`_sync_junction_amounts_after_compute`, then `_reconcile_module_amounts_from_
junctions`) so the assertion holds against real DB junction rows without the
full cashflow-engine seeding surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import (
    _auto_size_ddf_module,
    _ensure_ddf_junctions_for_all_projects,
    _per_project_capital_modules,
    _reconcile_module_amounts_from_junctions,
    _sync_junction_amounts_after_compute,
)
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import Deal, DealStatus, ProjectType, Scenario, UseLine
from app.models.org import Organization
from app.models.project import Project


async def _seed_two_projects(
    session: AsyncSession,
) -> tuple[Scenario, Project, Project]:
    org = Organization(name="DDF Rollup Org", slug="ddf-rollup-org")
    session.add(org)
    await session.flush()
    deal = Deal(org_id=org.id, name="DDF Rollup Deal", status=DealStatus.active)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        deal_id=deal.id,
        name="Base Case",
        version=1,
        project_type=ProjectType.acquisition,
    )
    session.add(scenario)
    await session.flush()
    p1 = Project(
        scenario_id=scenario.id,
        name="Project 1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    p2 = Project(
        scenario_id=scenario.id,
        name="Project 2",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    session.add_all([p1, p2])
    await session.flush()
    return scenario, p1, p2


async def _seed_project_uses(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    other_use: Decimal,
    dev_fee: Decimal,
) -> None:
    """One regular Use + one auto Dev Fee Use for a project."""
    session.add(UseLine(
        project_id=project_id,
        label="Hard Costs",
        amount=other_use,
        cost_category="hard",
    ))
    session.add(UseLine(
        project_id=project_id,
        label="Developer Fee (auto)",
        amount=dev_fee,
        cost_category="soft",
        is_auto_dev_fee=True,
        dev_fee_pct=Decimal("10"),
    ))
    await session.flush()


async def _add_debt(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    project_id: uuid.UUID,
    amount: Decimal,
    stack_position: int,
) -> CapitalModule:
    m = CapitalModule(
        scenario_id=scenario_id,
        label=f"Loan {stack_position}",
        vehicle_type="debt",
        stack_position=stack_position,
        source={"amount": str(amount)},
    )
    session.add(m)
    await session.flush()
    session.add(CapitalModuleProject(
        capital_module_id=m.id,
        project_id=project_id,
        amount=amount,
        auto_size=False,
    ))
    await session.flush()
    return m


async def _make_ddf(
    session: AsyncSession, scenario_id: uuid.UUID, primary_project_id: uuid.UUID
) -> CapitalModule:
    """DDF module attached ONLY to the primary project — the pre-fix shape."""
    m = CapitalModule(
        scenario_id=scenario_id,
        label="Deferred Developer Fee",
        vehicle_type="deferred_developer_fee",
        stack_position=99,
        source={"amount": "0", "auto_size": True},
        carry={"carry_type": "none"},
    )
    session.add(m)
    await session.flush()
    session.add(CapitalModuleProject(
        capital_module_id=m.id,
        project_id=primary_project_id,
        amount=Decimal("0"),
        auto_size=True,
    ))
    await session.flush()
    return m


async def _run_per_project_sizing(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    projects: list[Project],
) -> None:
    """Replay the compute loop's DDF sizing steps for each project."""
    for project in projects:
        modules = await _per_project_capital_modules(
            session, scenario_id, project.id
        )
        use_lines = list((await session.execute(
            select(UseLine).where(UseLine.project_id == project.id)
        )).scalars())
        _auto_size_ddf_module(modules, use_lines)
        await session.flush()
        await _sync_junction_amounts_after_compute(
            session, scenario_id, project.id, modules
        )
        await session.flush()
    await _reconcile_module_amounts_from_junctions(session, scenario_id)
    await session.flush()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_ddf_junctions_attaches_all_projects_and_is_idempotent(
    session: AsyncSession,
):
    scenario, p1, p2 = await _seed_two_projects(session)
    ddf = await _make_ddf(session, scenario.id, p1.id)

    await _ensure_ddf_junctions_for_all_projects(session, scenario.id, [p1, p2])

    juncs = list((await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id == ddf.id
        )
    )).scalars())
    assert {j.project_id for j in juncs} == {p1.id, p2.id}
    # New junction inherits the module's auto_size flag.
    assert all(j.auto_size for j in juncs)

    # Idempotent — a second call adds nothing.
    await _ensure_ddf_junctions_for_all_projects(session, scenario.id, [p1, p2])
    juncs_again = list((await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id == ddf.id
        )
    )).scalars())
    assert len(juncs_again) == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ddf_sizes_per_project_and_sums_across_rollup(
    session: AsyncSession,
):
    """P1 gap 20, P2 gap 10 → reconciled DDF module amount = 30, not the
    primary-only 20."""
    scenario, p1, p2 = await _seed_two_projects(session)
    ddf = await _make_ddf(session, scenario.id, p1.id)

    # P1: uses 100 (70 + 30 dev fee), debt 80 → gap 20, capped at dev fee 30 → 20
    await _seed_project_uses(session, p1.id, other_use=Decimal("70"), dev_fee=Decimal("30"))
    await _add_debt(session, scenario.id, p1.id, Decimal("80"), stack_position=1)
    # P2: uses 100 (70 + 30 dev fee), debt 90 → gap 10, capped at dev fee 30 → 10
    await _seed_project_uses(session, p2.id, other_use=Decimal("70"), dev_fee=Decimal("30"))
    await _add_debt(session, scenario.id, p2.id, Decimal("90"), stack_position=2)

    await _ensure_ddf_junctions_for_all_projects(session, scenario.id, [p1, p2])
    await _run_per_project_sizing(session, scenario.id, [p1, p2])

    await session.refresh(ddf, ["source"])
    assert Decimal(str((ddf.source or {}).get("amount"))) == Decimal("30")

    # Per-project junction amounts reflect each project's own gap.
    juncs = {
        j.project_id: j.amount
        for j in (await session.execute(
            select(CapitalModuleProject).where(
                CapitalModuleProject.capital_module_id == ddf.id
            )
        )).scalars()
    }
    assert Decimal(str(juncs[p1.id])) == Decimal("20")
    assert Decimal(str(juncs[p2.id])) == Decimal("10")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_per_project_manual_override_is_respected(
    session: AsyncSession,
):
    """A project flipped to auto_size=False keeps its manual amount; the other
    project still auto-sizes."""
    scenario, p1, p2 = await _seed_two_projects(session)
    ddf = await _make_ddf(session, scenario.id, p1.id)

    await _seed_project_uses(session, p1.id, other_use=Decimal("70"), dev_fee=Decimal("30"))
    await _add_debt(session, scenario.id, p1.id, Decimal("80"), stack_position=1)
    await _seed_project_uses(session, p2.id, other_use=Decimal("70"), dev_fee=Decimal("30"))
    await _add_debt(session, scenario.id, p2.id, Decimal("90"), stack_position=2)

    await _ensure_ddf_junctions_for_all_projects(session, scenario.id, [p1, p2])

    # Manual override on P2: fixed $15, auto_size off.
    p2_junc = (await session.execute(
        select(CapitalModuleProject).where(
            CapitalModuleProject.capital_module_id == ddf.id,
            CapitalModuleProject.project_id == p2.id,
        )
    )).scalar_one()
    p2_junc.amount = Decimal("15")
    p2_junc.auto_size = False
    await session.flush()

    await _run_per_project_sizing(session, scenario.id, [p1, p2])

    await session.refresh(ddf, ["source"])
    # P1 auto-sizes to 20; P2 stays at the manual 15 → 35 total.
    assert Decimal(str((ddf.source or {}).get("amount"))) == Decimal("35")
