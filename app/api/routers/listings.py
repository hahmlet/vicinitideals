"""Listing ingestion and conversion endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserId, DBSession
from app.models.org import User
from app.models.project import (
    Opportunity,
    ProjectCategory,
    ProjectSource,
    ProjectStatus,
    ScrapedListing,
)
from app.schemas.project import ProjectRead, ScrapedListingRead

router = APIRouter(tags=["listings"])


class ListingConvertRequest(BaseModel):
    name: str | None = None
    org_id: UUID | None = None


@router.get("/listings", response_model=list[ScrapedListingRead])
async def list_scraped_listings(
    session: DBSession,
    is_new: bool | None = Query(default=None),
    matches_criteria: bool | None = Query(default=None),
) -> list[ScrapedListing]:
    stmt = select(ScrapedListing).order_by(ScrapedListing.scraped_at.desc())
    if is_new is not None:
        stmt = stmt.where(ScrapedListing.is_new == is_new)
    if matches_criteria is not None:
        stmt = stmt.where(ScrapedListing.matches_saved_criteria == matches_criteria)

    result = await session.execute(stmt)
    return list(result.scalars())


@router.post(
    "/listings/{listing_id}/convert",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def convert_listing_to_project(
    listing_id: UUID,
    payload: ListingConvertRequest,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> Opportunity:
    listing = await session.get(ScrapedListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.linked_project_id is not None:
        existing_project = await session.get(Opportunity, listing.linked_project_id)
        if existing_project is not None:
            return existing_project

    org_id = payload.org_id
    if org_id is None:
        user = await session.get(User, current_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        org_id = user.org_id

    project_name = payload.name or listing.address_normalized or listing.address_raw or f"{listing.source.title()} listing"
    try:
        project_source = ProjectSource(str(listing.source))
    except ValueError:
        project_source = ProjectSource.user_generated

    opportunity = Opportunity(
        org_id=org_id,
        name=project_name,
        status=ProjectStatus.hypothetical,
        project_category=ProjectCategory.proposed,
        source=project_source,
        created_by_user_id=current_user_id,
    )
    session.add(opportunity)
    await session.flush()

    listing.linked_project_id = opportunity.id
    listing.is_new = False
    await session.flush()
    await session.refresh(opportunity)
    return opportunity
