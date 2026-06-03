"""Tests for app/services/stabilization_milestone.py.

The reserve windows in cashflow (IR, ODR, OR) depend on a present and
anchored ``operation_stabilized`` milestone. These tests pin the
foolproofing layer that ensures the milestone exists with a sensible
predecessor.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project
from app.services.stabilization_milestone import (
    DEFAULT_STABILIZATION_DURATION_DAYS,
    ensure_stabilization_milestone,
    stabilization_anchor_is_set,
)
from tests.conftest import seed_deal_model, seed_opportunity, seed_org


async def _make_project(session: AsyncSession) -> Project:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model = await seed_deal_model(session, opp, user)
    project = Project(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=opp.id,
        name="Test Project",
    )
    session.add(project)
    await session.flush()
    return project


def _add_milestone(
    session: AsyncSession,
    project: Project,
    mtype: MilestoneType,
    sequence_order: int,
    duration_days: int = 30,
    trigger_milestone_id: uuid.UUID | None = None,
) -> Milestone:
    m = Milestone(
        project_id=project.id,
        milestone_type=mtype,
        duration_days=duration_days,
        sequence_order=sequence_order,
        trigger_milestone_id=trigger_milestone_id,
    )
    session.add(m)
    return m


@pytest.mark.integration
async def test_creates_when_missing_anchors_to_lease_up(session: AsyncSession):
    project = await _make_project(session)
    close = _add_milestone(session, project, MilestoneType.close, 1)
    construction = _add_milestone(
        session, project, MilestoneType.construction, 2,
        duration_days=180, trigger_milestone_id=None,
    )
    lease_up = _add_milestone(
        session, project, MilestoneType.operation_lease_up, 3,
        duration_days=120, trigger_milestone_id=None,
    )
    await session.flush()

    created = await ensure_stabilization_milestone(session, project)

    assert created.milestone_type == MilestoneType.operation_stabilized
    assert created.duration_days == DEFAULT_STABILIZATION_DURATION_DAYS
    assert created.trigger_milestone_id == lease_up.id
    assert created.sequence_order == 4


@pytest.mark.integration
async def test_falls_back_to_construction_when_no_lease_up(session: AsyncSession):
    project = await _make_project(session)
    _add_milestone(session, project, MilestoneType.close, 1)
    construction = _add_milestone(session, project, MilestoneType.construction, 2)
    await session.flush()

    created = await ensure_stabilization_milestone(session, project)
    assert created.trigger_milestone_id == construction.id


@pytest.mark.integration
async def test_falls_back_to_close_for_pure_acquisition(session: AsyncSession):
    project = await _make_project(session)
    close = _add_milestone(session, project, MilestoneType.close, 1)
    await session.flush()

    created = await ensure_stabilization_milestone(session, project)
    assert created.trigger_milestone_id == close.id


@pytest.mark.integration
async def test_no_predecessor_creates_unanchored(session: AsyncSession):
    project = await _make_project(session)
    await session.flush()

    created = await ensure_stabilization_milestone(session, project)
    assert created.trigger_milestone_id is None
    assert created.target_date is None
    assert stabilization_anchor_is_set(created) is False


@pytest.mark.integration
async def test_idempotent_when_milestone_already_present(session: AsyncSession):
    project = await _make_project(session)
    pre_existing = _add_milestone(
        session, project, MilestoneType.operation_stabilized, 5,
        duration_days=1825,
    )
    await session.flush()

    returned = await ensure_stabilization_milestone(session, project)
    assert returned.id == pre_existing.id

    count = (await session.execute(
        select(Milestone)
        .where(Milestone.project_id == project.id)
        .where(Milestone.milestone_type == MilestoneType.operation_stabilized)
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.integration
async def test_anchor_helper_recognizes_target_date(session: AsyncSession):
    from datetime import date

    project = await _make_project(session)
    m = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.operation_stabilized,
        duration_days=1825,
        sequence_order=1,
        target_date=date(2027, 1, 1),
    )
    assert stabilization_anchor_is_set(m) is True
