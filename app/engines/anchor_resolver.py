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

from typing import Any
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


async def resolve_project_start_dates(
    scenario: Scenario, session: AsyncSession
) -> dict[UUID, Any]:
    """Phase 2d1: compute each Project's effective start date by walking the
    anchor chain and applying per-edge offsets.

    Semantics for a single anchor edge ``(child ← parent, anchor_milestone, +offset)``:

        child.start = parent.anchor_milestone.end_date
                    + offset_months
                    + offset_days

    Projects without an anchor row fall through to the root milestone's
    ``target_date`` for their own milestone chain (legacy behavior). The
    anchor_milestone lookup walks the parent's ORM milestone chain to get
    the end date using the usual ``computed_end()`` resolver.

    Returns::

        {project_id: date | None}

    The caller (``compute_cash_flows``) passes this map into the per-project
    engine invocation so anchored projects can override their own root
    milestone date. If ``anchor_milestone_id`` is missing / NULL (anchor
    row exists but no specific milestone picked), the function falls back
    to the parent project's earliest milestone's target_date. Errors in
    chain traversal return None for that project, letting the engine use
    its own defaults.

    For zero-anchor scenarios (every prod deal today) returns an empty
    dict — short-circuit fast path.
    """
    from datetime import date as _date, timedelta

    from app.models.milestone import Milestone as _Milestone

    projects = sorted(list(scenario.projects), key=lambda p: p.created_at)
    if not projects:
        return {}

    project_ids = [p.id for p in projects]
    anchors = list(
        (
            await session.execute(
                select(ProjectAnchor).where(ProjectAnchor.project_id.in_(project_ids))
            )
        ).scalars()
    )
    if not anchors:
        return {}

    anchor_by_child: dict[UUID, ProjectAnchor] = {a.project_id: a for a in anchors}

    # Load every milestone for every project on the scenario in one query so
    # chain-walking (child's anchor_milestone → parent's milestone with
    # ``computed_end()``) doesn't incur a per-lookup round-trip.
    all_milestones = list(
        (
            await session.execute(
                select(_Milestone).where(_Milestone.project_id.in_(project_ids))
            )
        ).scalars()
    )
    ms_by_id: dict[UUID, _Milestone] = {m.id: m for m in all_milestones}
    ms_by_project: dict[UUID, list[_Milestone]] = {}
    for m in all_milestones:
        ms_by_project.setdefault(m.project_id, []).append(m)

    # Topo order — anchored projects run AFTER their parent so the parent's
    # resolved date is available when the child resolves.
    ordered = await ordered_projects(scenario, session)
    resolved: dict[UUID, Any] = {}

    def _add_offset(d: _date, months: int, days: int) -> _date:
        # Month arithmetic: add N months naively by bumping the month index
        # (and rolling into years), then clamp the day to the target month's
        # last day so e.g. Jan 31 + 1 month = Feb 28/29.
        y = d.year
        m = d.month + int(months or 0)
        while m > 12:
            y += 1
            m -= 12
        while m < 1:
            y -= 1
            m += 12
        # Clamp day
        import calendar
        last_day = calendar.monthrange(y, m)[1]
        day = min(d.day, last_day)
        base = _date(y, m, day)
        return base + timedelta(days=int(days or 0))

    for project in ordered:
        anchor = anchor_by_child.get(project.id)
        if anchor is None:
            continue  # uses project's own root milestone target_date

        parent_id = anchor.anchor_project_id
        # The specific milestone on the parent to pivot off. If not set,
        # fall back to the parent's earliest milestone (by sequence_order).
        pivot: _Milestone | None = None
        if anchor.anchor_milestone_id:
            pivot = ms_by_id.get(anchor.anchor_milestone_id)
        if pivot is None:
            parent_ms = sorted(
                ms_by_project.get(parent_id, []),
                key=lambda m: (m.sequence_order or 0, m.created_at),
            )
            pivot = parent_ms[0] if parent_ms else None
        if pivot is None:
            continue  # parent has no milestones — can't resolve; leave unset

        # If the pivot milestone belongs to the parent, resolve its
        # end-date via the trigger-chain walker. The pivot's own project
        # may have been date-overridden by this function already — but the
        # ORM-level ``computed_end()`` reads ``target_date`` directly, which
        # we do NOT mutate on the in-memory ORM object. Instead we pass a
        # temporary milestone_map that reflects the resolved root-date
        # override for parent projects visited earlier in the topo walk.
        #
        # For v1 keep it simple: use the pivot's ORM computed_end() as-is.
        # Propagated shifts through a chain of 3+ projects require pivot
        # milestones at each intermediate node and will work as long as the
        # intermediate project's root date has been updated in the DB
        # (which the caller does via the milestone_dates override).
        parent_ms_map = {m.id: m for m in ms_by_project.get(parent_id, [])}
        end = pivot.computed_end(milestone_map=parent_ms_map)
        if end is None:
            continue

        resolved[project.id] = _add_offset(
            end, int(anchor.offset_months or 0), int(anchor.offset_days or 0)
        )

    return resolved


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
