"""Cross-project timeline resolution (Phase 0 of multi-project compute).

A ``ProjectAnchor`` row says "project P starts relative to anchor_project's
anchor_milestone plus an offset." Multi-project scenarios may form chains
(P3 → P2 → P1). This module:

1. Returns a compute order where every anchor's parent is visited before
   its child (topological sort). Cycles are rejected at write time, but we
   re-validate here because the UI is only one of several write paths.

2. (Phase 2d1, deferred) Resolves each project's effective start date by
   walking the anchor chain and applying offsets. The current engine reads
   milestone dates directly from ORM; once anchor-driven date resolution
   is implemented, the resolver will seed per-project milestone overrides
   that the engine consumes before phase planning.

For scenarios with zero anchors (every production deal today), this module
short-circuits to ``sorted(projects, key=created_at)`` — the exact same
order the engine used before Phase 2, so math is byte-identical.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Scenario
from app.models.project import Project, ProjectAnchor


class AnchorCycleError(ValueError):
    """Raised when ProjectAnchor rows form a cycle (P1 → P2 → P1)."""


async def ordered_projects(
    scenario: Scenario, session: AsyncSession
) -> list[Project]:
    """Return ``scenario.projects`` in anchor-topological compute order.

    Projects without an anchor come first (anchor-free roots), then anchored
    projects after their parent. Ties break by ``created_at``.

    Raises ``AnchorCycleError`` if the anchor graph has a cycle.
    """
    projects: list[Project] = sorted(
        list(scenario.projects), key=lambda p: p.created_at
    )
    if not projects:
        return []

    project_ids = [p.id for p in projects]
    anchors = list(
        (
            await session.execute(
                select(ProjectAnchor).where(ProjectAnchor.project_id.in_(project_ids))
            )
        ).scalars()
    )

    # Zero-anchor fast path — same as the legacy sort.
    if not anchors:
        return projects

    # Build edges: anchor_project_id → project_id
    by_id: dict[UUID, Project] = {p.id: p for p in projects}
    parent_of: dict[UUID, UUID] = {a.project_id: a.anchor_project_id for a in anchors}

    _check_no_cycles(parent_of, project_ids)

    # Topological sort: Kahn's algorithm. In-degree = 1 for anchored projects,
    # 0 for roots. Ties within a degree broken by created_at (inherited from
    # the initial sort above — Python sort is stable).
    in_degree: dict[UUID, int] = {pid: 0 for pid in project_ids}
    for child_id, parent_id in parent_of.items():
        if parent_id in in_degree:
            in_degree[child_id] += 1

    ordered: list[Project] = []
    ready = [p for p in projects if in_degree[p.id] == 0]
    # Reverse-map: parent_id → list of child_ids (so we can decrement in-degree)
    children: dict[UUID, list[UUID]] = {}
    for child_id, parent_id in parent_of.items():
        children.setdefault(parent_id, []).append(child_id)

    while ready:
        p = ready.pop(0)
        ordered.append(p)
        for child_id in children.get(p.id, []):
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                ready.append(by_id[child_id])
                ready.sort(key=lambda pp: pp.created_at)

    if len(ordered) != len(projects):
        # Should have been caught by _check_no_cycles; defensive guard.
        raise AnchorCycleError(
            f"Unresolvable ProjectAnchor graph on scenario {scenario.id}"
        )
    return ordered


def _check_no_cycles(parent_of: dict[UUID, UUID], project_ids: list[UUID]) -> None:
    """DFS each project's anchor chain; raise AnchorCycleError on a back-edge."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[UUID, int] = {pid: WHITE for pid in project_ids}

    def visit(pid: UUID, path: list[UUID]) -> None:
        if color.get(pid) == GRAY:
            # Back-edge → cycle
            cycle = " → ".join(str(x) for x in path + [pid])
            raise AnchorCycleError(f"ProjectAnchor cycle detected: {cycle}")
        if color.get(pid) == BLACK:
            return
        color[pid] = GRAY
        parent = parent_of.get(pid)
        if parent is not None and parent in color:
            visit(parent, path + [pid])
        color[pid] = BLACK

    for pid in project_ids:
        visit(pid, [])
