"""unify_rj_bond collapses per-project bond slices into one shared module.

Seeds a scenario whose bond was split into separate modules (one junction
each) — the shape the consolidation script produced — plus a stray 5.5%
slice, a float-earnings child pointing at a doomed slice, and an explicitly
routed use-line. After ``unify`` there must be exactly one bond module
carrying every project's slice, all at 6.0%, with the float parent and the
use-line routing repointed to the survivor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import (
    Deal,
    DealStatus,
    ProjectType,
    Scenario,
    UseLine,
)
from app.models.org import Organization
from app.models.project import Project
from app.scripts.unify_rj_bond import unify

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]

LABEL = "Raymond James Bond"


async def _seed(session: AsyncSession):
    org = Organization(name="Org", slug="org")
    session.add(org)
    await session.flush()
    deal = Deal(org_id=org.id, name="Unified", status=DealStatus.active)
    session.add(deal)
    await session.flush()
    scn = Scenario(
        deal_id=deal.id, name="Pool", version=1, project_type=ProjectType.acquisition
    )
    session.add(scn)
    await session.flush()

    # Four projects, each with its own bond slice; one slice stray at 5.5%.
    rates = ["6.0", "6.0", "6.0", "5.5"]
    amounts = ["1000000", "2000000", "3000000", "4000000"]
    projects: list[Project] = []
    bonds: list[CapitalModule] = []
    for i, (rate, amt) in enumerate(zip(rates, amounts)):
        p = Project(
            scenario_id=scn.id,
            name=f"P{i}",
            created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
        )
        session.add(p)
        await session.flush()
        projects.append(p)
        m = CapitalModule(
            scenario_id=scn.id,
            label=LABEL,
            vehicle_type="debt",
            stack_position=1 if i < 2 else 2,
            source={"amount": amt, "interest_rate_pct": rate},
            exit_terms={},
        )
        session.add(m)
        await session.flush()
        bonds.append(m)
        session.add(
            CapitalModuleProject(
                capital_module_id=m.id,
                project_id=p.id,
                amount=Decimal(amt),
                auto_size=False,
            )
        )
    await session.flush()

    # Float child points at the stray 5.5% slice (will be deleted on merge).
    doomed = bonds[3]
    fm = CapitalModule(
        scenario_id=scn.id,
        label="Float Earnings",
        vehicle_type="float_earnings",
        stack_position=5,
        source={"amount": "0", "parent_module_id": str(doomed.id)},
    )
    session.add(fm)

    # An explicitly routed use-line on a doomed slice.
    ul = UseLine(
        project_id=projects[2].id,
        label="Hard Costs",
        amount=Decimal("500000"),
        source_capital_module_id=bonds[2].id,
    )
    session.add(ul)
    await session.flush()
    return scn, fm, ul


async def test_unify_collapses_to_single_bond(session: AsyncSession):
    scn, fm, ul = await _seed(session)

    summary = await unify(session, scn.id)

    assert summary["merged"] == 3
    assert summary["slices"] == 4
    assert Decimal(summary["total"]) == Decimal("10000000")

    bonds = list(
        (
            await session.execute(
                select(CapitalModule).where(
                    CapitalModule.scenario_id == scn.id,
                    CapitalModule.label == LABEL,
                )
            )
        ).scalars()
    )
    assert len(bonds) == 1
    survivor = bonds[0]
    assert survivor.source["interest_rate_pct"] == "6.0"
    assert Decimal(survivor.source["amount"]) == Decimal("10000000")
    assert survivor.exit_terms["vehicle"] == "maturity"

    # All four project slices now hang off the survivor.
    slices = list(
        (
            await session.execute(
                select(CapitalModuleProject).where(
                    CapitalModuleProject.capital_module_id == survivor.id
                )
            )
        ).scalars()
    )
    assert len(slices) == 4

    # Float parent + use-line routing repointed.
    await session.refresh(fm)
    await session.refresh(ul)
    assert fm.source["parent_module_id"] == str(survivor.id)
    assert ul.source_capital_module_id == survivor.id


async def test_unify_idempotent(session: AsyncSession):
    scn, _fm, _ul = await _seed(session)
    await unify(session, scn.id)
    second = await unify(session, scn.id)
    assert second["merged"] == 0
