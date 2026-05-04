"""Project and project-parcel API endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserId, DBSession
from app.models.capital import CapitalModule
from app.models.cashflow import OperationalOutputs
from app.models.deal import DealModel, IncomeStream, OperatingExpenseLine
from app.models.org import Organization, ProjectVisibility
from app.models.parcel import (
    Parcel,
    ParcelTransformation,
    ParcelTransformationType,
    ProjectParcelRelationship,
)
from app.models.project import Opportunity, Project
from app.schemas.org import ProjectVisibilityRead
from app.schemas.parcel import ParcelTransformationBase, ParcelTransformationRead, ProjectParcelRead
from app.schemas.project import ProjectCreate, ProjectRead
from app.scrapers.arcgis import lookup_gresham_candidates

router = APIRouter(tags=["projects"])


class ProjectVisibilityUpdate(BaseModel):
    hidden: bool = False


class ProjectParcelAttachRequest(BaseModel):
    parcel_id: UUID | None = None
    apn: str | None = None
    address: str | None = None
    relationship_type: ProjectParcelRelationship = ProjectParcelRelationship.unchanged
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_locator(self) -> "ProjectParcelAttachRequest":
        if self.parcel_id is None and not (self.apn and self.apn.strip()) and not (self.address and self.address.strip()):
            raise ValueError("Provide `parcel_id`, `apn`, or `address` to attach a parcel.")
        return self


class ProjectParcelUpdateRequest(BaseModel):
    relationship_type: ProjectParcelRelationship | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_update(self) -> "ProjectParcelUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class ParcelTransformationUpdateRequest(BaseModel):
    transformation_type: ParcelTransformationType | None = None
    input_apns: list[str] | None = None
    output_apns: list[str] | None = None
    effective_lot_sqft: Decimal | None = None
    notes: str | None = None
    effective_date: date | None = None

    @model_validator(mode="after")
    def _validate_update(self) -> "ParcelTransformationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


async def _get_project_or_404(session: DBSession, project_id: UUID) -> Opportunity:
    project = await session.get(Opportunity, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _resolve_project_deal_model(session: DBSession, project_id: UUID) -> DealModel | None:
    # Find Scenarios via Projects that reference this Opportunity
    result = await session.execute(
        select(DealModel)
        .options(selectinload(DealModel.operational_outputs))
        .join(Project, Project.scenario_id == DealModel.id)
        .where(Project.opportunity_id == project_id)
        .order_by(DealModel.is_active.desc(), DealModel.version.desc(), DealModel.created_at.desc())
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


async def _upsert_parcel_from_lookup(session: DBSession, parcel_data: dict) -> Parcel:
    parcel = (
        await session.execute(select(Parcel).where(Parcel.apn == parcel_data["apn"]))
    ).scalar_one_or_none()
    if parcel is None:
        parcel = Parcel(apn=parcel_data["apn"])
        session.add(parcel)

    for field, value in parcel_data.items():
        setattr(parcel, field, value)

    parcel.scraped_at = datetime.now(UTC)
    await session.flush()
    return parcel


async def _resolve_parcel_for_attachment(
    session: DBSession,
    payload: ProjectParcelAttachRequest,
) -> Parcel:
    if payload.parcel_id is not None:
        parcel = await session.get(Parcel, payload.parcel_id)
        if parcel is None:
            raise HTTPException(status_code=404, detail="Parcel not found")
        return parcel

    if payload.apn and payload.apn.strip():
        parcel = (
            await session.execute(select(Parcel).where(Parcel.apn == payload.apn.strip().upper()))
        ).scalar_one_or_none()
        if parcel is not None:
            return parcel

    live_matches = await lookup_gresham_candidates(apn=payload.apn, address=payload.address)
    if not live_matches:
        raise HTTPException(status_code=404, detail="Parcel not found via lookup")
    if len(live_matches) > 1:
        raise HTTPException(status_code=409, detail="Multiple parcels matched the lookup; refine by APN.")
    return await _upsert_parcel_from_lookup(session, live_matches[0])


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    session: DBSession,
    current_user_id: CurrentUserId,
    org_id: UUID | None = Query(default=None),
    include_hidden: bool = Query(default=False),
) -> list[Opportunity]:
    stmt = select(Opportunity).order_by(Opportunity.created_at.desc())
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
    return list(result.scalars())


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: DBSession) -> Opportunity:
    organization = await session.get(Organization, payload.org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    project = Opportunity(**payload.model_dump())
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


def _build_parcel_link(
    project_id: UUID,
    parcel: Parcel,
    rel_type: ProjectParcelRelationship = ProjectParcelRelationship.unchanged,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build a ProjectParcelRead-compatible dict from the new single-FK model."""
    return {
        "project_id": project_id,
        "parcel_id": parcel.id,
        "relationship_type": rel_type,
        "notes": notes,
        "parcel": parcel,
    }


@router.get("/projects/{project_id}/parcels", response_model=list[ProjectParcelRead])
async def list_project_parcels(project_id: UUID, session: DBSession) -> list[dict]:
    opp = await _get_project_or_404(session, project_id)
    if opp.parcel_id is None:
        return []
    parcel = await session.get(Parcel, opp.parcel_id)
    if parcel is None:
        return []
    return [_build_parcel_link(project_id, parcel)]


@router.post(
    "/projects/{project_id}/parcels",
    response_model=ProjectParcelRead,
    status_code=status.HTTP_201_CREATED,
)
async def attach_parcel_to_project(
    project_id: UUID,
    payload: ProjectParcelAttachRequest,
    session: DBSession,
) -> dict:
    opp = await _get_project_or_404(session, project_id)
    parcel = await _resolve_parcel_for_attachment(session, payload)
    opp.parcel_id = parcel.id
    session.add(opp)
    await session.flush()
    return _build_parcel_link(project_id, parcel, payload.relationship_type, payload.notes)


@router.patch("/projects/{project_id}/parcels/{parcel_id}", response_model=ProjectParcelRead)
async def update_project_parcel(
    project_id: UUID,
    parcel_id: UUID,
    payload: ProjectParcelUpdateRequest,
    session: DBSession,
) -> dict:
    opp = await _get_project_or_404(session, project_id)
    if opp.parcel_id != parcel_id:
        raise HTTPException(status_code=404, detail="Project parcel link not found")
    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    rel = payload.relationship_type or ProjectParcelRelationship.unchanged
    return _build_parcel_link(project_id, parcel, rel, payload.notes)


@router.delete("/projects/{project_id}/parcels/{parcel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_parcel(
    project_id: UUID,
    parcel_id: UUID,
    session: DBSession,
) -> Response:
    opp = await _get_project_or_404(session, project_id)
    if opp.parcel_id != parcel_id:
        raise HTTPException(status_code=404, detail="Project parcel link not found")
    opp.parcel_id = None
    session.add(opp)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/transformations",
    response_model=list[ParcelTransformationRead],
)
async def list_project_transformations(
    project_id: UUID,
    session: DBSession,
) -> list[ParcelTransformation]:
    await _get_project_or_404(session, project_id)

    result = await session.execute(
        select(ParcelTransformation)
        .where(ParcelTransformation.project_id == project_id)
        .order_by(ParcelTransformation.effective_date.asc(), ParcelTransformation.id.asc())
    )
    return list(result.scalars())


@router.post(
    "/projects/{project_id}/transformations",
    response_model=ParcelTransformationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_transformation(
    project_id: UUID,
    payload: ParcelTransformationBase,
    session: DBSession,
) -> ParcelTransformation:
    await _get_project_or_404(session, project_id)

    transformation = ParcelTransformation(project_id=project_id, **payload.model_dump())
    session.add(transformation)
    await session.flush()
    await session.refresh(transformation)
    return transformation


@router.patch(
    "/projects/{project_id}/transformations/{transformation_id}",
    response_model=ParcelTransformationRead,
)
async def update_project_transformation(
    project_id: UUID,
    transformation_id: UUID,
    payload: ParcelTransformationUpdateRequest,
    session: DBSession,
) -> ParcelTransformation:
    await _get_project_or_404(session, project_id)

    transformation = await session.get(ParcelTransformation, transformation_id)
    if transformation is None or transformation.project_id != project_id:
        raise HTTPException(status_code=404, detail="Parcel transformation not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(transformation, field, value)

    await session.flush()
    await session.refresh(transformation)
    return transformation


@router.delete(
    "/projects/{project_id}/transformations/{transformation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_transformation(
    project_id: UUID,
    transformation_id: UUID,
    session: DBSession,
) -> Response:
    await _get_project_or_404(session, project_id)

    transformation = await session.get(ParcelTransformation, transformation_id)
    if transformation is None or transformation.project_id != project_id:
        raise HTTPException(status_code=404, detail="Parcel transformation not found")

    await session.delete(transformation)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
