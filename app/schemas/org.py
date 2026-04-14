"""Organization, User, ProjectVisibility schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class OrganizationBase(BaseModel):
    name: str
    slug: str


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    name: str
    display_color: str | None = None


class UserCreate(UserBase):
    org_id: uuid.UUID


class UserRead(UserBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ProjectVisibility
# ---------------------------------------------------------------------------

class ProjectVisibilityBase(BaseModel):
    hidden: bool = False


class ProjectVisibilityCreate(ProjectVisibilityBase):
    project_id: uuid.UUID
    user_id: uuid.UUID


class ProjectVisibilityRead(ProjectVisibilityBase):
    project_id: uuid.UUID
    user_id: uuid.UUID

    model_config = {"from_attributes": True}
