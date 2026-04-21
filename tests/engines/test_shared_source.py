"""Shared-Source detection + junction-amount lookup tests.

Phase 2f plumbing: confirm the engine's shared-Source helpers correctly
identify modules attached to >1 projects via the capital_module_projects
junction, and correctly return per-project amounts from that junction.

The engine's auto-sizing doesn't yet read junction.amount (Phase 2c1
deferred pending a deeper refactor that also touches the writeback path).
These tests lock down the read-side semantics so the overlay work has a
stable target.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import (
    _per_project_capital_modules,
    is_shared_source,
    junction_amount_for,
)
from app.models.capital import CapitalModule, CapitalModuleProject, FunderType
from app.models.deal import Deal, DealStatus, ProjectType, Scenario
from app.models.org import Organization
from app.models.project import Project


async def _seed_basics(session: AsyncSession) -> tuple[Scenario, Project, Project]:
    """Org → Deal → Scenario with two Projects. Returns (scenario, p1, p2)."""
    org = Organization(name="Test Org", slug="test-org")
    session.add(org)
    await session.flush()
    deal = Deal(
        org_id=org.id,
        name="Multi-Project Test Deal",
        status=DealStatus.active,
    )
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
        deal_type=ProjectType.acquisition.value,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    p2 = Project(
        scenario_id=scenario.id,
        name="Project 2",
        deal_type=ProjectType.acquisition.value,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    session.add_all([p1, p2])
    await session.flush()
    return scenario, p1, p2


async def _make_module(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    label: str,
    funder_type: FunderType = FunderType.permanent_debt,
    stack_position: int = 0,
    amount: Decimal = Decimal("1000000"),
) -> CapitalModule:
    m = CapitalModule(
        scenario_id=scenario_id,
        label=label,
        funder_type=funder_type,
        stack_position=stack_position,
        source={"amount": str(amount)},
    )
    session.add(m)
    await session.flush()
    return m


async def _attach(
    session: AsyncSession,
    module_id: uuid.UUID,
    project_id: uuid.UUID,
    amount: Decimal,
) -> None:
    j = CapitalModuleProject(
        capital_module_id=module_id,
        project_id=project_id,
        amount=amount,
        auto_size=False,
    )
    session.add(j)
    await session.flush()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_is_shared_source_false_when_single_project(
    session: AsyncSession,
):
    scenario, p1, _p2 = await _seed_basics(session)
    m = await _make_module(session, scenario.id, "Perm Loan")
    await _attach(session, m.id, p1.id, Decimal("5000000"))
    assert await is_shared_source(session, m.id) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_is_shared_source_true_when_two_projects(
    session: AsyncSession,
):
    scenario, p1, p2 = await _seed_basics(session)
    m = await _make_module(session, scenario.id, "Shared Loan")
    await _attach(session, m.id, p1.id, Decimal("5000000"))
    await _attach(session, m.id, p2.id, Decimal("3000000"))
    assert await is_shared_source(session, m.id) is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_junction_amount_returns_per_project_value(
    session: AsyncSession,
):
    scenario, p1, p2 = await _seed_basics(session)
    m = await _make_module(session, scenario.id, "Shared Loan")
    await _attach(session, m.id, p1.id, Decimal("5000000"))
    await _attach(session, m.id, p2.id, Decimal("3000000"))

    amt_p1 = await junction_amount_for(session, m.id, p1.id)
    amt_p2 = await junction_amount_for(session, m.id, p2.id)
    assert amt_p1 == Decimal("5000000")
    assert amt_p2 == Decimal("3000000")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_junction_amount_none_when_not_attached(
    session: AsyncSession,
):
    scenario, p1, p2 = await _seed_basics(session)
    m = await _make_module(session, scenario.id, "P1-only Loan")
    await _attach(session, m.id, p1.id, Decimal("5000000"))
    assert await junction_amount_for(session, m.id, p2.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_per_project_loader_filters_by_junction(
    session: AsyncSession,
):
    """A module attached only to P1 is NOT visible to P2's loader."""
    scenario, p1, p2 = await _seed_basics(session)
    m_p1 = await _make_module(
        session, scenario.id, "P1-only Loan", stack_position=0
    )
    m_both = await _make_module(
        session, scenario.id, "Shared Loan", stack_position=1
    )
    await _attach(session, m_p1.id, p1.id, Decimal("5000000"))
    await _attach(session, m_both.id, p1.id, Decimal("2000000"))
    await _attach(session, m_both.id, p2.id, Decimal("3000000"))

    p1_modules = await _per_project_capital_modules(
        session, scenario.id, p1.id
    )
    p2_modules = await _per_project_capital_modules(
        session, scenario.id, p2.id
    )

    assert {m.id for m in p1_modules} == {m_p1.id, m_both.id}
    assert {m.id for m in p2_modules} == {m_both.id}
    # Stack position ordering preserved for P1
    assert [m.label for m in p1_modules] == ["P1-only Loan", "Shared Loan"]
