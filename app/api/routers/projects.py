"""Project API endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserId, DBSession
from app.models.capital import CapitalModule
from app.models.cashflow import OperationalOutputs
from app.models.deal import Scenario, IncomeStream, OperatingExpenseLine
from app.models.org import Organization, ProjectVisibility
from app.models.project import Opportunity, Project
from app.schemas.org import ProjectVisibilityRead
from app.schemas.project import ProjectCreate, ProjectRead

router = APIRouter(tags=["projects"])


class ProjectVisibilityUpdate(BaseModel):
    hidden: bool = False


async def _get_project_or_404(session: DBSession, project_id: UUID) -> Opportunity:
    project = await session.get(Opportunity, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _resolve_project_deal_model(session: DBSession, project_id: UUID) -> Scenario | None:
    # Find Scenarios via Projects that reference this Opportunity
    result = await session.execute(
        select(Scenario)
        .options(selectinload(Scenario.operational_outputs))
        .join(Project, Project.scenario_id == Scenario.id)
        .where(Project.opportunity_id == project_id)
        .order_by(Scenario.is_active.desc(), Scenario.version.desc(), Scenario.created_at.desc())
    )
    models = list(result.scalars().unique())
    if not models:
        return None

    active_model = next((model for model in models if model.is_active), None)
    return active_model or models[0]


async def _count_line_items(
    session: DBSession,
    deal_id: UUID,
    row_model: type[Any],
) -> int:
    """Count line items (IncomeStream/OperatingExpenseLine) via the default dev Project."""
    default_proj = (
        await session.execute(
            select(Project)
            .where(Project.scenario_id == deal_id)
            .order_by(Project.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if default_proj is None:
        return 0
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(row_model)
                .where(row_model.project_id == default_proj.id)
            )
        ).scalar_one()
    )


async def _count_capital_modules(session: DBSession, deal_id: UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(CapitalModule)
                .where(CapitalModule.scenario_id == deal_id)
            )
        ).scalar_one()
    )


def _serialize_project_outputs(outputs: OperationalOutputs | None) -> dict[str, Any] | None:
    if outputs is None:
        return None

    return {
        "total_project_cost": outputs.total_project_cost,
        "equity_required": outputs.equity_required,
        "total_timeline_months": outputs.total_timeline_months,
        "noi_stabilized": outputs.noi_stabilized,
        "cap_rate_on_cost_pct": outputs.cap_rate_on_cost_pct,
        "dscr": outputs.dscr,
        "project_irr_levered": outputs.project_irr_levered,
        "project_irr_unlevered": outputs.project_irr_unlevered,
        "computed_at": outputs.computed_at,
    }


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    session: DBSession,
    current_user_id: CurrentUserId,
    org_id: UUID | None = Query(default=None),
    include_hidden: bool = Query(default=False),
) -> list[Opportunity]:
    stmt = select(Opportunity).order_by(Opportunity.last_seen_at.desc())
    if org_id is not None:
        stmt = stmt.where(Opportunity.org_id == org_id)

    if not include_hidden:
        stmt = (
            stmt.outerjoin(
                ProjectVisibility,
                and_(
                    ProjectVisibility.project_id == Opportunity.id,
                    ProjectVisibility.user_id == current_user_id,
                ),
            )
            .where(
                or_(
                    ProjectVisibility.hidden.is_(None),
                    ProjectVisibility.hidden.is_(False),
                )
            )
        )

    result = await session.execute(stmt)
    # Explicitly construct ProjectRead to map opp_status → status.
    # Opportunity.status holds scraper-sourced strings ('Active') which don't
    # match the ProjectStatus enum; opp_status holds the canonical enum value.
    opps = list(result.scalars())
    return [
        ProjectRead(
            id=p.id,
            name=p.name,
            status=p.opp_status,
            project_category=p.project_category,
            org_id=p.org_id,
            created_by_user_id=p.created_by_user_id,
            created_at=None,
        )
        for p in opps
    ]


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: DBSession) -> Opportunity:
    organization = await session.get(Organization, payload.org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    data = payload.model_dump()
    # "manual" is the canonical origin label for hand-created opportunities —
    # the UI HTMX path and email ingest use it too. Keep all three aligned.
    data["source"] = data.get("source") or "manual"
    project = Opportunity(**data)
    session.add(project)
    await session.flush()
    await session.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, session: DBSession) -> Opportunity:
    project = await session.get(Opportunity, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}/summary")
async def get_project_summary(project_id: UUID, session: DBSession) -> dict[str, Any]:
    project = await _get_project_or_404(session, project_id)
    deal_model = await _resolve_project_deal_model(session, project_id)

    income_stream_count = 0
    expense_line_count = 0
    capital_module_count = 0
    if deal_model is not None:
        income_stream_count = await _count_line_items(session, deal_model.id, IncomeStream)
        expense_line_count = await _count_line_items(session, deal_model.id, OperatingExpenseLine)
        capital_module_count = await _count_capital_modules(session, deal_model.id)

    return {
        "id": str(project.id),
        "name": project.name,
        "status": project.status,
        "source": project.source,
        "active_deal_model_id": str(deal_model.id) if deal_model is not None else None,
        "income_stream_count": income_stream_count,
        "expense_line_count": expense_line_count,
        "capital_module_count": capital_module_count,
        "outputs": _serialize_project_outputs(
            deal_model.operational_outputs if deal_model is not None else None
        ),
    }


@router.patch("/projects/{project_id}/visibility", response_model=ProjectVisibilityRead)
async def update_project_visibility(
    project_id: UUID,
    payload: ProjectVisibilityUpdate,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> ProjectVisibility:
    project = await session.get(Opportunity, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    visibility = await session.get(
        ProjectVisibility,
        {"project_id": project_id, "user_id": current_user_id},
    )
    if visibility is None:
        visibility = ProjectVisibility(
            project_id=project_id,
            user_id=current_user_id,
            hidden=payload.hidden,
        )
        session.add(visibility)
    else:
        visibility.hidden = payload.hidden

    await session.flush()
    return visibility
