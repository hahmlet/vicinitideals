"""Ensure every project has an ``operation_stabilized`` milestone.

Reserve windows (Interest Reserve, Operating Deficit Reserve, Operating
Reserve) all reference the Stabilization milestone to mark where one window
ends and the next begins. Without an anchor for Stabilization, the windows
fall back to implicit phase-duration math that can drift when a user edits
upstream durations without realizing it controls the reserve coverage
downstream.

This helper is the foolproofing layer: any time a project is loaded for the
builder or compute, ensure the milestone is present. Create it anchored to
the natural predecessor (lease-up > construction-side > pre-development >
close) so it shows up in the timeline with a sensible default the user can
edit.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project


_STABILIZATION_PREDECESSOR_PRIORITY: tuple[MilestoneType, ...] = (
    MilestoneType.operation_lease_up,
    MilestoneType.construction,
    MilestoneType.pre_development,
    MilestoneType.close,
)

DEFAULT_STABILIZATION_DURATION_DAYS = 1825  # 5 years; matches DEFAULT_DURATIONS.


def _coerce_type(raw) -> MilestoneType | None:
    if isinstance(raw, MilestoneType):
        return raw
    if raw is None:
        return None
    text = str(raw).replace("MilestoneType.", "")
    try:
        return MilestoneType(text)
    except ValueError:
        return None


async def ensure_stabilization_milestone(
    session: AsyncSession,
    project: Project,
    *,
    duration_days: int = DEFAULT_STABILIZATION_DURATION_DAYS,
) -> Milestone:
    """Return the project's ``operation_stabilized`` milestone, creating one
    anchored to the natural predecessor when missing.

    Idempotent: returns the existing milestone unchanged when one is found.
    The new milestone is added to the session and flushed so callers reading
    milestones in the same request see it. No commit is issued here — the
    caller's transaction owns commit/rollback.
    """
    existing = list((await session.execute(
        select(Milestone).where(Milestone.project_id == project.id)
    )).scalars())

    by_type: dict[MilestoneType, Milestone] = {}
    for m in existing:
        mtype = _coerce_type(m.milestone_type)
        if mtype is None:
            continue
        if mtype == MilestoneType.operation_stabilized:
            return m
        by_type.setdefault(mtype, m)

    predecessor: Milestone | None = None
    for mtype in _STABILIZATION_PREDECESSOR_PRIORITY:
        if mtype in by_type:
            predecessor = by_type[mtype]
            break

    max_seq = max((m.sequence_order for m in existing), default=0)

    new = Milestone(
        project_id=project.id,
        milestone_type=MilestoneType.operation_stabilized,
        duration_days=duration_days,
        sequence_order=max_seq + 1,
        trigger_milestone_id=predecessor.id if predecessor is not None else None,
        trigger_offset_days=0,
    )
    session.add(new)
    await session.flush()
    return new


def stabilization_anchor_is_set(milestone: Milestone) -> bool:
    """True when the milestone has a resolvable anchor (trigger chain or
    explicit ``target_date``). UI warns when False so the user knows the
    reserve windows downstream depend on it."""
    if milestone.trigger_milestone_id is not None:
        return True
    return milestone.target_date is not None
