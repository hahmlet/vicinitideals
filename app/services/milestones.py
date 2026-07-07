"""Shared milestone timeline service — trigger-chain creation and CRUD.

Extracted from the timeline wizard (app/api/routers/ui_wizards.py) so the
wizard and the REST/MCP milestone router (app/api/routers/milestones.py)
share ONE code path for milestone creation and trigger-chain wiring.

Two-pass creation contract (matches the original wizard behavior):
  Pass 1 — instantiate every milestone with its duration + target_date
           (only the anchor carries a target_date).
  Pass 2 — wire ``trigger_milestone_id`` so each non-anchor milestone
           starts at the end of the previous one in submitted order.

Without the trigger chain, ``Milestone.computed_start()`` returns None for
non-anchor milestones and the cashflow engine falls back to the legacy
``OperationalInputs.*_months`` scalars (NULL → 1-month fallback), which
collapses the carry-type math. See the production bug fixed in 5d5caf4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import Milestone, MilestoneType


class MilestoneTriggerError(ValueError):
    """Raised when a trigger reference is invalid (missing, cross-project,
    self-referential, or would create a cycle)."""


@dataclass(frozen=True)
class MilestoneSpec:
    """One milestone to create in a chain.

    ``target_date`` set = anchor milestone (calendar-pinned, no trigger).
    Exactly one spec in a chain should carry a target_date; the rest are
    wired to trigger off the previous milestone in list order.
    """

    milestone_type: MilestoneType
    duration_days: int = 0
    target_date: date | None = None
    label: str | None = None


async def clear_project_timeline(session: AsyncSession, project_id: UUID) -> None:
    """Delete all milestones and any ProjectAnchor rows for the project.

    Used by the wizard before re-creating the timeline: the user is setting
    a manual start date, so any prior anchor linkage is detached (they can
    re-anchor later via the Timeline Anchors panel).
    """
    from app.models.project import ProjectAnchor

    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    await session.execute(sa_delete(ProjectAnchor).where(ProjectAnchor.project_id == project_id))
    await session.flush()


def wire_trigger_chain(created: list[Milestone]) -> None:
    """Pass 2: build the trigger chain in list order.

    Each non-anchor milestone triggers off the previous one with offset=0 so
    its start date equals the prior milestone's end date
    (prev.start + prev.duration_days). Anchor milestones (target_date set)
    never receive a trigger.
    """
    prev: Milestone | None = None
    for row in created:
        if row.target_date is not None:  # anchor — calendar-pinned
            prev = row
            continue
        if prev is not None:
            row.trigger_milestone_id = prev.id
            row.trigger_offset_days = 0
        prev = row


async def create_milestone_chain(
    session: AsyncSession,
    project_id: UUID,
    specs: list[MilestoneSpec],
) -> list[Milestone]:
    """Create milestones for ``specs`` in order and wire the trigger chain.

    Pass 1 creates rows (flushed so every Milestone has a primary key before
    trigger refs are assigned); Pass 2 wires ``trigger_milestone_id``.
    """
    created: list[Milestone] = []
    for seq, spec in enumerate(specs):
        row = Milestone(
            project_id=project_id,
            milestone_type=spec.milestone_type,
            target_date=spec.target_date,
            duration_days=spec.duration_days,
            sequence_order=seq,
            label=spec.label,
        )
        session.add(row)
        created.append(row)

    # Flush so every Milestone gets a primary key before we wire trigger refs.
    await session.flush()

    wire_trigger_chain(created)
    return created


# ---------------------------------------------------------------------------
# Single-row CRUD helpers (REST/MCP surface)
# ---------------------------------------------------------------------------

async def list_project_milestones(
    session: AsyncSession, project_id: UUID
) -> list[Milestone]:
    """All milestones for a project in canonical (sequence_order, id) order."""
    rows = (await session.execute(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.sequence_order, Milestone.id)
    )).scalars()
    return list(rows)


def resolve_milestone_dates(
    rows: list[Milestone],
) -> dict[UUID, tuple[date | None, date | None]]:
    """Resolve (computed_start, computed_end) for every row via the chain map."""
    milestone_map = {r.id: r for r in rows}
    return {
        r.id: (r.computed_start(milestone_map), r.computed_end(milestone_map))
        for r in rows
    }


async def _validate_trigger(
    session: AsyncSession,
    project_id: UUID,
    trigger_milestone_id: UUID,
    milestone_id: UUID | None,
) -> None:
    """Validate a trigger reference: same project, not self, no cycle."""
    if milestone_id is not None and trigger_milestone_id == milestone_id:
        raise MilestoneTriggerError("A milestone cannot trigger off itself.")

    rows = await list_project_milestones(session, project_id)
    by_id = {r.id: r for r in rows}
    trigger = by_id.get(trigger_milestone_id)
    if trigger is None:
        raise MilestoneTriggerError(
            "trigger_milestone_id does not reference a milestone on this project."
        )

    # Cycle check: walk the chain upward from the proposed trigger. If we
    # reach the milestone being edited, the edit would close a loop and
    # computed_start() would recurse forever.
    if milestone_id is not None:
        seen: set[UUID] = set()
        cursor: Milestone | None = trigger
        while cursor is not None and cursor.trigger_milestone_id is not None:
            if cursor.trigger_milestone_id == milestone_id:
                raise MilestoneTriggerError(
                    "Trigger chain would create a cycle."
                )
            if cursor.id in seen:  # pre-existing loop — stop walking
                break
            seen.add(cursor.id)
            cursor = by_id.get(cursor.trigger_milestone_id)


async def create_project_milestone(
    session: AsyncSession,
    project_id: UUID,
    *,
    milestone_type: MilestoneType,
    duration_days: int = 0,
    target_date: date | None = None,
    sequence_order: int | None = None,
    label: str | None = None,
    trigger_milestone_id: UUID | None = None,
    trigger_offset_days: int = 0,
) -> Milestone:
    """Create one milestone on a project (REST create path).

    ``trigger_milestone_id`` (when given) must reference a milestone on the
    same project. When ``sequence_order`` is omitted the milestone is
    appended after the current maximum.
    """
    if trigger_milestone_id is not None:
        await _validate_trigger(session, project_id, trigger_milestone_id, None)

    if sequence_order is None:
        max_seq = (await session.execute(
            select(Milestone.sequence_order)
            .where(Milestone.project_id == project_id)
            .order_by(Milestone.sequence_order.desc())
            .limit(1)
        )).scalar_one_or_none()
        sequence_order = (max_seq if max_seq is not None else -1) + 1

    row = Milestone(
        project_id=project_id,
        milestone_type=milestone_type,
        duration_days=duration_days,
        target_date=target_date,
        sequence_order=sequence_order,
        label=label,
        trigger_milestone_id=trigger_milestone_id,
        trigger_offset_days=trigger_offset_days,
    )
    session.add(row)
    await session.flush()
    return row


async def update_project_milestone(
    session: AsyncSession,
    milestone: Milestone,
    fields: dict,
) -> Milestone:
    """Apply a partial update; validates any new trigger reference."""
    if fields.get("trigger_milestone_id") is not None:
        await _validate_trigger(
            session,
            milestone.project_id,
            fields["trigger_milestone_id"],
            milestone.id,
        )
    for key, value in fields.items():
        setattr(milestone, key, value)
    await session.flush()
    return milestone


async def delete_project_milestone(
    session: AsyncSession, milestone: Milestone
) -> None:
    """Delete a milestone. Dependents' ``trigger_milestone_id`` is set NULL
    by the FK's ``ondelete="SET NULL"`` — they become chain heads that no
    longer resolve a computed_start until re-wired."""
    await session.delete(milestone)
    await session.flush()
