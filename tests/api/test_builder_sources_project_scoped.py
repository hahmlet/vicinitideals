"""Builder Sources panel is scoped to the active project.

Regression: ``_load_builder_data`` loaded *every* scenario CapitalModule for
the Sources table, so on a multi-project scenario each project's tab listed
all projects' Sources (a phantom ~$54M sum) even though the balance pill —
which reads junction-scoped totals — stayed correct. The displayed
``capital_modules`` list must be filtered to the active project's junction
attachments. With ``project_id=None`` (aggregate view) it still returns the
full stack.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui import _load_builder_data
from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import Deal, DealStatus, ProjectType, Scenario
from app.models.org import Organization
from app.models.project import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def _seed_two_project_scenario(
    session: AsyncSession,
) -> tuple[Scenario, Project, Project, CapitalModule, CapitalModule]:
    """Scenario with two projects; one module per project, each attached to
    only its own project via the junction."""
    org = Organization(name="Test Org", slug="test-org")
    session.add(org)
    await session.flush()
    deal = Deal(org_id=org.id, name="Unified Deal", status=DealStatus.active)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        deal_id=deal.id,
        name="Combined Pool",
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

    m1 = CapitalModule(
        scenario_id=scenario.id,
        label="P1 Bond Slice",
        vehicle_type="debt",
        stack_position=0,
        source={"amount": "1000000"},
    )
    m2 = CapitalModule(
        scenario_id=scenario.id,
        label="P2 Bond Slice",
        vehicle_type="debt",
        stack_position=1,
        source={"amount": "9000000"},
    )
    session.add_all([m1, m2])
    await session.flush()
    session.add_all(
        [
            CapitalModuleProject(
                capital_module_id=m1.id,
                project_id=p1.id,
                amount=Decimal("1000000"),
                auto_size=False,
            ),
            CapitalModuleProject(
                capital_module_id=m2.id,
                project_id=p2.id,
                amount=Decimal("9000000"),
                auto_size=False,
            ),
        ]
    )
    await session.flush()
    return scenario, p1, p2, m1, m2


async def test_sources_scoped_to_active_project(session: AsyncSession):
    scenario, p1, p2, m1, m2 = await _seed_two_project_scenario(session)

    p1_data = await _load_builder_data(session, scenario.id, project_id=p1.id)
    p2_data = await _load_builder_data(session, scenario.id, project_id=p2.id)

    assert {m.id for m in p1_data["capital_modules"]} == {m1.id}
    assert {m.id for m in p2_data["capital_modules"]} == {m2.id}


async def test_no_project_id_defaults_to_first_project(session: AsyncSession):
    # _load_builder_data always resolves to a single project — with no
    # project_id it falls back to the earliest-created one (p1 here), so its
    # Sources stay scoped (only p1's module), never the full pooled stack.
    scenario, p1, p2, m1, m2 = await _seed_two_project_scenario(session)

    data = await _load_builder_data(session, scenario.id, project_id=None)

    assert {m.id for m in data["capital_modules"]} == {m1.id}
