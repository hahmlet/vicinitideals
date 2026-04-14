"""User-related API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from vicinitideals.api.deps import DBSession
from vicinitideals.models.org import Organization, User
from vicinitideals.schemas.org import UserRead

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserRead])
async def list_all_users(session: DBSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.name.asc()))
    return list(result.scalars())


@router.get("/orgs/{org_id}/users", response_model=list[UserRead])
async def list_org_users(org_id: UUID, session: DBSession) -> list[User]:
    organization = await session.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await session.execute(
        select(User).where(User.org_id == org_id).order_by(User.name.asc())
    )
    return list(result.scalars())
