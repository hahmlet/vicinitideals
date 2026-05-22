"""Resolve CapitalModule.active_from_milestone_id / active_to_milestone_id FKs
from the legacy active_phase_start / active_phase_end string fields.

The string fields ("acquisition", "close", "operation_stabilized", and milestone-
key variants from the wizard) are mapped to MilestoneType enum values, then the
service looks up a milestone of that type on one of the scenario's projects and
writes the FK back to the module. Multi-project scenarios pick the milestone on
the project with the lowest id (deterministic); operators can re-pick via the
debt edit form when ambiguous.

Called from the wizard finalize handler and the debt edit form handlers so any
write to active_phase_start / active_phase_end keeps the FKs in lock-step.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project


# Wizard / legacy phase-key values → MilestoneType enum values they should map to.
# Mirrors the table embedded in alembic/versions/0095 — if you change one,
# change both. Unmapped values resolve to None (FK stays cleared).
_APS_TO_MILESTONE_TYPE: dict[str, MilestoneType] = {
    "acquisition":          MilestoneType.close,
    "close":                MilestoneType.close,
    "offer_made":           MilestoneType.offer_made,
    "under_contract":       MilestoneType.under_contract,
    "pre_construction":     MilestoneType.pre_development,
    "pre_development":      MilestoneType.pre_development,
    "construction":         MilestoneType.construction,
    "lease_up":             MilestoneType.operation_lease_up,
    "operation_lease_up":   MilestoneType.operation_lease_up,
    "stabilized":           MilestoneType.operation_stabilized,
    "operation_stabilized": MilestoneType.operation_stabilized,
    "exit":                 MilestoneType.divestment,
    "divestment":           MilestoneType.divestment,
}


def map_aps_to_milestone_type(aps_value: str | None) -> MilestoneType | None:
    if not aps_value:
        return None
    return _APS_TO_MILESTONE_TYPE.get(str(aps_value))


async def _find_milestone_id_for_scenario(
    session: AsyncSession,
    scenario_id: uuid.UUID,
    ms_type: MilestoneType,
) -> uuid.UUID | None:
    """Return the deterministic milestone id for this type within the scenario."""
    rows = (await session.execute(
        select(Milestone.id)
        .join(Project, Project.id == Milestone.project_id)
        .where(Project.scenario_id == scenario_id)
        .where(Milestone.milestone_type == ms_type)
        .order_by(Project.id, Milestone.sequence_order, Milestone.id)
        .limit(1)
    )).first()
    return rows[0] if rows else None


async def sync_milestone_fks_for_module(
    session: AsyncSession,
    cm: CapitalModule,
) -> None:
    """Populate active_from_milestone_id / active_to_milestone_id on `cm`
    based on the current values of active_phase_start / active_phase_end."""
    from_type = map_aps_to_milestone_type(cm.active_phase_start)
    if from_type is not None:
        cm.active_from_milestone_id = await _find_milestone_id_for_scenario(
            session, cm.scenario_id, from_type
        )
    else:
        cm.active_from_milestone_id = None

    to_type = map_aps_to_milestone_type(cm.active_phase_end)
    if to_type is not None:
        cm.active_to_milestone_id = await _find_milestone_id_for_scenario(
            session, cm.scenario_id, to_type
        )
    else:
        cm.active_to_milestone_id = None


async def sync_milestone_fks_for_scenario(
    session: AsyncSession,
    scenario_id: uuid.UUID,
) -> int:
    """Sync FKs for every CapitalModule in a scenario. Returns rows touched."""
    modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == scenario_id)
    )).scalars())
    for cm in modules:
        await sync_milestone_fks_for_module(session, cm)
    return len(modules)
