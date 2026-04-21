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
