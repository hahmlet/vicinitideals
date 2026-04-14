"""Deal import/export schema endpoints for agent workflows."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from vicinitideals.api.deps import CurrentUserId, DBSession
from vicinitideals.exporters import DEAL_JSON_SCHEMA, import_deal_from_json
from vicinitideals.exporters.deal_export import export_deal_json, import_deal_json
from vicinitideals.models.org import Organization, User

router = APIRouter(tags=["deals"])


async def _resolve_import_context(session: DBSession, current_user_id) -> tuple[Any, Any | None]:
    user = await session.get(User, current_user_id)
    if user is not None:
        return user.org_id, user.id

    org_id = (
        await session.execute(select(Organization.id).order_by(Organization.created_at.asc()))
    ).scalar_one_or_none()
    if org_id is None:
        raise HTTPException(status_code=404, detail="No organization available for deal import")
    return org_id, None


@router.get("/deals/schema")
async def get_deal_schema() -> dict[str, Any]:
    return DEAL_JSON_SCHEMA


@router.get("/deals/{deal_id}/export/json")
async def export_deal(deal_id: UUID, session: DBSession) -> dict[str, Any]:
    """Export a full deal as portable deal-v1 JSON."""
    try:
        return await export_deal_json(session=session, deal_id=deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/deals/import/json", status_code=status.HTTP_201_CREATED)
async def import_deal_v1(
    payload: dict[str, Any],
    session: DBSession,
    current_user_id: CurrentUserId,
) -> dict[str, Any]:
    """Import a deal from a deal-v1 portable JSON export."""
    org_id, created_by_user_id = await _resolve_import_context(session, current_user_id)
    try:
        deal = await import_deal_json(
            session=session,
            org_id=org_id,
            payload=payload,
            created_by_user_id=created_by_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deal_id": str(deal.id)}


@router.post("/deals/import", status_code=status.HTTP_201_CREATED)
async def import_deal_payload(
    payload: dict[str, Any],
    session: DBSession,
    current_user_id: CurrentUserId,
) -> dict[str, Any]:
    org_id, created_by_user_id = await _resolve_import_context(session, current_user_id)

    try:
        result = await import_deal_from_json(
            session=session,
            org_id=org_id,
            payload=payload,
            created_by_user_id=created_by_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "project_id": str(result.project.id),
        "deal_model_id": str(result.model.id),
        "counts": result.counts,
        "warnings": result.warnings,
    }
