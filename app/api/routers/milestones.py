"""Milestone + DrawSource REST CRUD — REST/MCP parity with the builder UI.

Deals built via the JSON API previously had no way to create timeline
milestones (trigger chains) or draw-schedule sources — both were UI-only.
Without milestones the cashflow engine falls back to the legacy
``OperationalInputs.*_months`` scalars (NULL → 1-month phases). These
endpoints close the gap.

Routes mirror the sibling conventions in app/api/routers/models.py:
``model_id`` resolves Scenario → default Project (list/create), and item
lookups accept any Project belonging to the scenario. Route function names
become MCP tool names (FastApiMCP derives tools from the OpenAPI schema),
so they are named as verbs: list_milestones, create_milestone, ...
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.api.deps import DBSession
from app.api.routers.models import _get_deal_or_404, _get_default_project_for_deal
from app.models.capital import DrawSource
from app.models.milestone import Milestone
from app.schemas.capital import DrawSourceCreate, DrawSourceRead, DrawSourceUpdate
from app.schemas.milestone import MilestoneCreate, MilestoneRead, MilestoneUpdate
from app.services import draw_sources as draw_source_service
from app.services import milestones as milestone_service
from app.services.milestones import MilestoneTriggerError

router = APIRouter(tags=["models"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_milestone_or_404(
    session: DBSession,
    model_id: UUID,
    milestone_id: UUID,
) -> Milestone:
    """Fetch a milestone scoped to any project of this scenario (mirrors
    ``_get_use_line_or_404`` in models.py)."""
    await _get_deal_or_404(session, model_id)
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    from app.models.project import Project

    project = await session.get(Project, milestone.project_id)
    if project is None or project.scenario_id != model_id:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone


async def _milestone_reads_for_project(
    session: DBSession, project_id: UUID
) -> list[MilestoneRead]:
    """Serialize a project's milestones with chain-resolved dates."""
    rows = await milestone_service.list_project_milestones(session, project_id)
    dates = milestone_service.resolve_milestone_dates(rows)
    reads: list[MilestoneRead] = []
    for row in rows:
        read = MilestoneRead.model_validate(row)
        read.computed_start_date, read.computed_end_date = dates[row.id]
        reads.append(read)
    return reads


async def _milestone_read_with_dates(
    session: DBSession, milestone: Milestone
) -> MilestoneRead:
    """Serialize one milestone, resolving its dates through the full chain."""
    assert milestone.project_id is not None
    rows = await milestone_service.list_project_milestones(
        session, milestone.project_id
    )
    dates = milestone_service.resolve_milestone_dates(rows)
    read = MilestoneRead.model_validate(milestone)
    read.computed_start_date, read.computed_end_date = dates.get(
        milestone.id, (None, None)
    )
    return read


# ---------------------------------------------------------------------------
# Milestones (timeline trigger chains)
# ---------------------------------------------------------------------------

@router.get("/models/{model_id}/milestones", response_model=list[MilestoneRead])
async def list_milestones(model_id: UUID, session: DBSession) -> list[MilestoneRead]:
    """List the model's timeline milestones with chain-resolved start/end dates."""
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    return await _milestone_reads_for_project(session, project.id)


@router.post(
    "/models/{model_id}/milestones",
    response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_milestone(
    model_id: UUID,
    payload: MilestoneCreate,
    session: DBSession,
) -> MilestoneRead:
    """Create a milestone. Set ``target_date`` on the anchor; chain the rest
    via ``trigger_milestone_id`` so the engine resolves real phase windows."""
    await _get_deal_or_404(session, model_id)
    project = await _get_default_project_for_deal(session, model_id)
    try:
        milestone = await milestone_service.create_project_milestone(
            session,
            project.id,
            milestone_type=payload.milestone_type,
            duration_days=payload.duration_days,
            target_date=payload.target_date,
            sequence_order=payload.sequence_order,
            label=payload.label,
            trigger_milestone_id=payload.trigger_milestone_id,
            trigger_offset_days=payload.trigger_offset_days,
        )
    except MilestoneTriggerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _milestone_read_with_dates(session, milestone)


@router.put("/models/{model_id}/milestones/{milestone_id}", response_model=MilestoneRead)
@router.patch("/models/{model_id}/milestones/{milestone_id}", response_model=MilestoneRead)
async def update_milestone(
    model_id: UUID,
    milestone_id: UUID,
    payload: MilestoneUpdate,
    session: DBSession,
) -> MilestoneRead:
    """Partially update a milestone (duration, trigger rewiring, reorder)."""
    milestone = await _get_milestone_or_404(session, model_id, milestone_id)
    try:
        await milestone_service.update_project_milestone(
            session, milestone, payload.model_dump(exclude_unset=True)
        )
    except MilestoneTriggerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _milestone_read_with_dates(session, milestone)


@router.delete(
    "/models/{model_id}/milestones/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_milestone(
    model_id: UUID,
    milestone_id: UUID,
    session: DBSession,
) -> Response:
    """Delete a milestone. Milestones that triggered off it lose their
    trigger (FK is SET NULL) and must be re-wired to resolve dates again."""
    milestone = await _get_milestone_or_404(session, model_id, milestone_id)
    await milestone_service.delete_project_milestone(session, milestone)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Draw sources (draw-schedule funding sources)
# ---------------------------------------------------------------------------

async def _get_draw_source_or_404(
    session: DBSession,
    model_id: UUID,
    source_id: UUID,
) -> DrawSource:
    await _get_deal_or_404(session, model_id)
    ds = await draw_source_service.get_draw_source_for_model(
        session, model_id, source_id
    )
    if ds is None:
        raise HTTPException(status_code=404, detail="Draw source not found")
    return ds


@router.get("/models/{model_id}/draw-sources", response_model=list[DrawSourceRead])
async def list_draw_sources(model_id: UUID, session: DBSession) -> list[DrawSource]:
    """List the model's draw-schedule funding sources in draw order."""
    await _get_deal_or_404(session, model_id)
    return await draw_source_service.list_scenario_draw_sources(session, model_id)


@router.post(
    "/models/{model_id}/draw-sources",
    response_model=DrawSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_draw_source(
    model_id: UUID,
    payload: DrawSourceCreate,
    session: DBSession,
) -> DrawSource:
    """Add a draw source. Active window is a milestone span
    (``active_from_milestone`` → ``active_to_milestone``)."""
    await _get_deal_or_404(session, model_id)
    return await draw_source_service.create_draw_source(
        session,
        model_id,
        label=payload.label,
        source_type=payload.source_type,
        draw_every_n_months=payload.draw_every_n_months,
        annual_interest_rate=payload.annual_interest_rate,
        active_from_milestone=payload.active_from_milestone,
        active_to_milestone=payload.active_to_milestone,
        active_from_offset_days=payload.active_from_offset_days,
        active_to_offset_days=payload.active_to_offset_days,
        total_commitment=payload.total_commitment,
        project_id=payload.project_id,
        capital_module_id=payload.capital_module_id,
        sort_order=payload.sort_order,
    )


@router.put("/models/{model_id}/draw-sources/{source_id}", response_model=DrawSourceRead)
@router.patch("/models/{model_id}/draw-sources/{source_id}", response_model=DrawSourceRead)
async def update_draw_source(
    model_id: UUID,
    source_id: UUID,
    payload: DrawSourceUpdate,
    session: DBSession,
) -> DrawSource:
    """Partially update a draw source (window, commitment, rate, order)."""
    ds = await _get_draw_source_or_404(session, model_id, source_id)
    return await draw_source_service.update_draw_source(
        session, ds, payload.model_dump(exclude_unset=True)
    )


@router.delete(
    "/models/{model_id}/draw-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_draw_source(
    model_id: UUID,
    source_id: UUID,
    session: DBSession,
) -> Response:
    """Delete a draw source row."""
    ds = await _get_draw_source_or_404(session, model_id, source_id)
    await draw_source_service.delete_draw_source(session, ds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
