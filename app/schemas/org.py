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
    # None until the user finishes onboarding: /register creates the row with
    # no organisation and sends them to the wizard (`User.org_id` is nullable
    # for exactly this). A required UUID here turned every such user into a
    # 500 on GET /api/users -- caught by the post-deploy smoke check on
    # 2026-09-15, the first evening a registered-but-not-onboarded user existed.
    org_id: uuid.UUID | None = None
    is_org_admin: bool = False
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
