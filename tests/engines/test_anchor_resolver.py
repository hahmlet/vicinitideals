"""Unit tests for cross-project anchor topological sort + cycle detection."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.engines.anchor_resolver import (
    AnchorCycleError,
    _check_no_cycles,
    ordered_projects,
)


def _p(n: int, seconds_after: int = 0) -> SimpleNamespace:
    """Minimal stand-in for a Project ORM row for ordering tests."""
    return SimpleNamespace(
        id=uuid.UUID(int=n),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        + timedelta(seconds=seconds_after),
    )


class _FakeSession:
    def __init__(self, anchors: list[SimpleNamespace]):
        self._anchors = anchors

    async def execute(self, _stmt):
        anchors = self._anchors

        class _Res:
            def scalars(self_inner):
                return anchors

        return _Res()


def _scenario(projects: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.UUID(int=999), projects=projects)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_zero_anchors_sorts_by_created_at():
    # P2 created before P1 — expect P2 first.
    p1 = _p(1, seconds_after=10)
    p2 = _p(2, seconds_after=0)
    session = _FakeSession(anchors=[])
    out = await ordered_projects(_scenario([p1, p2]), session)
    assert [p.id for p in out] == [p2.id, p1.id]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_linear_chain_topo_order():
    # P1 (root), P2 anchored to P1, P3 anchored to P2.
    # created_at order: P3 (0s), P2 (5s), P1 (10s) — inverse of desired.
    p1 = _p(1, 10)
    p2 = _p(2, 5)
    p3 = _p(3, 0)
    anchors = [
        SimpleNamespace(project_id=p2.id, anchor_project_id=p1.id),
        SimpleNamespace(project_id=p3.id, anchor_project_id=p2.id),
    ]
    out = await ordered_projects(_scenario([p1, p2, p3]), _FakeSession(anchors))
    assert [p.id for p in out] == [p1.id, p2.id, p3.id]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_two_chains_interleave_by_created_at():
    # Two independent roots P1 (t=0), P2 (t=5). P1a anchored to P1, P2a to P2.
    # Expected: roots first by created_at, then children.
    p1 = _p(1, 0)
    p2 = _p(2, 5)
    p1a = _p(3, 100)
    p2a = _p(4, 50)
    anchors = [
        SimpleNamespace(project_id=p1a.id, anchor_project_id=p1.id),
        SimpleNamespace(project_id=p2a.id, anchor_project_id=p2.id),
    ]
    out = await ordered_projects(
        _scenario([p1, p2, p1a, p2a]), _FakeSession(anchors)
    )
    order = [p.id for p in out]
    # roots first (p1, p2), then children in created_at order (p2a before p1a)
    assert order.index(p1.id) < order.index(p1a.id)
    assert order.index(p2.id) < order.index(p2a.id)


@pytest.mark.unit
def test_cycle_detection_rejects_two_node_cycle():
    a, b = uuid.UUID(int=1), uuid.UUID(int=2)
    parent_of = {a: b, b: a}
    with pytest.raises(AnchorCycleError):
        _check_no_cycles(parent_of, [a, b])


@pytest.mark.unit
def test_cycle_detection_rejects_three_node_cycle():
    a, b, c = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)
    parent_of = {a: b, b: c, c: a}
    with pytest.raises(AnchorCycleError):
        _check_no_cycles(parent_of, [a, b, c])


@pytest.mark.unit
def test_cycle_detection_passes_linear_chain():
    a, b, c = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)
    # c anchored to b, b anchored to a, a is root.
    parent_of = {c: b, b: a}
    _check_no_cycles(parent_of, [a, b, c])  # no raise


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2d1: resolve_project_start_dates
# ─────────────────────────────────────────────────────────────────────────────
#
# Integration tests with real ORM + SQLite fixtures. Cover three scenarios:
#   - zero anchors → empty dict (no-op fast path)
#   - single anchor with offset → child start = parent milestone end + offset
#   - missing anchor_milestone_id → falls back to parent's earliest milestone
# ─────────────────────────────────────────────────────────────────────────────

from datetime import date, timedelta, datetime, timezone as _tz
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.anchor_resolver import resolve_project_start_dates
from app.models.capital import CapitalModule, CapitalModuleProject, FunderType
from app.models.deal import Deal, DealStatus, ProjectType, Scenario
from app.models.milestone import Milestone, MilestoneType
from app.models.org import Organization
from app.models.project import Project, ProjectAnchor


async def _seed_two_projects(session: AsyncSession):
    """Scenario with two projects; return (scenario, p1, p2)."""
    org = Organization(name="Anchor Test Org", slug="anchor-test-org")
    session.add(org)
    await session.flush()
    deal = Deal(org_id=org.id, name="Anchor Test", status=DealStatus.active)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        deal_id=deal.id, name="Base", version=1, project_type=ProjectType.acquisition
    )
    session.add(scenario)
    await session.flush()
    p1 = Project(
        scenario_id=scenario.id,
        name="Project 1",
        deal_type=ProjectType.acquisition.value,
        created_at=datetime(2026, 1, 1, tzinfo=_tz.utc),
    )
    p2 = Project(
        scenario_id=scenario.id,
        name="Project 2",
        deal_type=ProjectType.acquisition.value,
        created_at=datetime(2026, 1, 2, tzinfo=_tz.utc),
    )
    session.add_all([p1, p2])
    await session.flush()
    # Refresh scenario so scenario.projects is populated from the ORM
    await session.refresh(scenario, ["projects"])
    return scenario, p1, p2


async def _add_close_milestone(
    session: AsyncSession, project: Project, target: date, duration_days: int = 30
) -> Milestone:
    """Add a 'close' milestone pinned to a target date."""
    m = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.close,
        target_date=target,
        duration_days=duration_days,
        sequence_order=1,
        label="Close",
    )
    session.add(m)
    await session.flush()
    return m


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_returns_empty_when_no_anchors(session: AsyncSession):
    scenario, p1, p2 = await _seed_two_projects(session)
    result = await resolve_project_start_dates(scenario, session)
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_applies_month_offset(session: AsyncSession):
    # P1 close pinned to 2026-06-01 with 30-day duration → close.end ≈ 2026-07-01.
    # Anchor P2 to P1.close + 6 months → P2 start = 2027-01-01.
    scenario, p1, p2 = await _seed_two_projects(session)
    close_p1 = await _add_close_milestone(session, p1, date(2026, 6, 1), 30)
    session.add(
        ProjectAnchor(
            project_id=p2.id,
            anchor_project_id=p1.id,
            anchor_milestone_id=close_p1.id,
            offset_months=6,
            offset_days=0,
        )
    )
    await session.flush()
    await session.refresh(scenario, ["projects"])
    result = await resolve_project_start_dates(scenario, session)
    assert p2.id in result
    # 2026-07-01 + 6 months = 2027-01-01
    assert result[p2.id] == date(2027, 1, 1)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_applies_day_offset(session: AsyncSession):
    scenario, p1, p2 = await _seed_two_projects(session)
    close_p1 = await _add_close_milestone(session, p1, date(2026, 6, 1), 30)
    session.add(
        ProjectAnchor(
            project_id=p2.id,
            anchor_project_id=p1.id,
            anchor_milestone_id=close_p1.id,
            offset_months=0,
            offset_days=14,
        )
    )
    await session.flush()
    await session.refresh(scenario, ["projects"])
    result = await resolve_project_start_dates(scenario, session)
    # 2026-07-01 + 14 days = 2026-07-15
    assert result[p2.id] == date(2026, 7, 15)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_combined_month_and_day_offset(session: AsyncSession):
    scenario, p1, p2 = await _seed_two_projects(session)
    close_p1 = await _add_close_milestone(session, p1, date(2026, 1, 15), 30)
    # close.end_date = 2026-02-14 (Jan 15 + 30 days)
    # + 3 months + 5 days → 2026-05-14 + 5 = 2026-05-19
    session.add(
        ProjectAnchor(
            project_id=p2.id,
            anchor_project_id=p1.id,
            anchor_milestone_id=close_p1.id,
            offset_months=3,
            offset_days=5,
        )
    )
    await session.flush()
    await session.refresh(scenario, ["projects"])
    result = await resolve_project_start_dates(scenario, session)
    assert result[p2.id] == date(2026, 5, 19)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resolve_falls_back_to_earliest_milestone_when_anchor_milestone_id_null(
    session: AsyncSession,
):
    scenario, p1, p2 = await _seed_two_projects(session)
    # Parent has two milestones; anchor without a specific milestone_id
    # should pivot off the earliest (sequence_order).
    m_early = Milestone(
        project_id=p1.id,
        milestone_type=MilestoneType.close,
        target_date=date(2026, 3, 1),
        duration_days=10,
        sequence_order=1,
    )
    m_late = Milestone(
        project_id=p1.id,
        milestone_type=MilestoneType.construction,
        target_date=date(2027, 1, 1),
        duration_days=30,
        sequence_order=2,
    )
    session.add_all([m_early, m_late])
    await session.flush()
    session.add(
        ProjectAnchor(
            project_id=p2.id,
            anchor_project_id=p1.id,
            anchor_milestone_id=None,
            offset_months=0,
            offset_days=0,
        )
    )
    await session.flush()
    await session.refresh(scenario, ["projects"])
    result = await resolve_project_start_dates(scenario, session)
    # Earliest = m_early; end = 2026-03-01 + 10d = 2026-03-11
    assert result[p2.id] == date(2026, 3, 11)
