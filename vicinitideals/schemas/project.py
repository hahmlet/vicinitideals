"""Project, PermitStub, ScrapedListing schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from vicinitideals.models.project import ProjectCategory, ProjectSource, ProjectStatus

_EXAMPLE_ORG_ID = "11111111-1111-1111-1111-111111111111"
_EXAMPLE_USER_ID = "22222222-2222-2222-2222-222222222222"
_EXAMPLE_PROJECT_ID = "33333333-3333-3333-3333-333333333333"
_EXAMPLE_CREATED_AT = "2026-04-03T12:00:00Z"


def _example_config(example: dict[str, object], *, from_attributes: bool = False) -> ConfigDict:
    config: dict[str, object] = {"json_schema_extra": {"examples": [example]}}
    if from_attributes:
        config["from_attributes"] = True
    return ConfigDict(**config)
from vicinitideals.schemas.scraped_listing import (
    ScrapedListingBase,
    ScrapedListingCreate,
    ScrapedListingRead,
)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class ProjectBase(BaseModel):
    name: str
    status: ProjectStatus = ProjectStatus.hypothetical
    project_category: ProjectCategory = ProjectCategory.proposed
    source: ProjectSource | None = None


class ProjectCreate(ProjectBase):
    org_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None

    model_config = _example_config(
        {
            "name": "Burnside Courtyard Apartments",
            "org_id": _EXAMPLE_ORG_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "status": "active",
            "project_category": "proposed",
            "source": "manual",
        }
    )


class ProjectRead(ProjectBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime

    model_config = _example_config(
        {
            "id": _EXAMPLE_PROJECT_ID,
            "name": "Burnside Courtyard Apartments",
            "org_id": _EXAMPLE_ORG_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "status": "active",
            "project_category": "proposed",
            "source": "manual",
            "created_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# PermitStub
# ---------------------------------------------------------------------------

class PermitStubBase(BaseModel):
    permit_number: str | None = None
    permit_url: str | None = None
    notes: str | None = None


class PermitStubCreate(PermitStubBase):
    project_id: uuid.UUID


class PermitStubRead(PermitStubBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ScrapedListing
# ---------------------------------------------------------------------------
