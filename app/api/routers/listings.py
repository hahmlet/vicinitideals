"""Listing ingestion and conversion endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserId, DBSession
from app.models.opportunity import Opportunity
from app.models.org import User
from app.schemas.project import ProjectRead, ScrapedListingRead

ScrapedListing = Opportunity

router = APIRouter(tags=["listings"])


class ListingConvertRequest(BaseModel):
    name: str | None = None
    org_id: UUID | None = None


@router.get("/listings", response_model=list[ScrapedListingRead])
async def list_scraped_listings(
    session: DBSession,
    is_new: bool | None = Query(default=None),
    matches_criteria: bool | None = Query(default=None),
) -> list[Opportunity]:
    stmt = select(Opportunity).order_by(Opportunity.last_seen_at.desc())
    if is_new is not None:
        stmt = stmt.where(Opportunity.is_new == is_new)
    if matches_criteria is not None:
        stmt = stmt.where(Opportunity.matches_saved_criteria == matches_criteria)

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
    listing = await session.get(Opportunity, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Listing IS the opportunity — already promoted if org_id is set
    if listing.org_id is not None:
        return listing

    org_id = payload.org_id
    if org_id is None:
        user = await session.get(User, current_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        org_id = user.org_id

    listing.org_id = org_id
    listing.name = payload.name or listing.address_normalized or listing.address_raw or f"{listing.source.title()} listing"
    listing.opp_status = "hypothetical"
    listing.project_category = "proposed"
    listing.promotion_source = "manual"
    listing.created_by_user_id = current_user_id
    listing.is_new = False
    await session.flush()
    await session.refresh(listing)
    return listing
