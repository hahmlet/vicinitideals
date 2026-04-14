"""Portfolio, PortfolioProject, GanttEntry schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from vicinitideals.models.portfolio import GanttPhase


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class PortfolioBase(BaseModel):
    name: str


class PortfolioCreate(PortfolioBase):
    org_id: uuid.UUID


class PortfolioRead(PortfolioBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime
    project_count: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PortfolioProject
# ---------------------------------------------------------------------------

class PortfolioProjectBase(BaseModel):
    scenario_id: uuid.UUID | None = None
    start_date: date | None = None
    capital_contribution: Decimal | None = None


class PortfolioProjectCreate(PortfolioProjectBase):
    portfolio_id: uuid.UUID
    project_id: uuid.UUID


class PortfolioProjectRead(PortfolioProjectBase):
    portfolio_id: uuid.UUID
    project_id: uuid.UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GanttEntry
# ---------------------------------------------------------------------------

class GanttEntryBase(BaseModel):
    phase: GanttPhase
    start_date: date
    end_date: date


class GanttEntryCreate(GanttEntryBase):
    portfolio_id: uuid.UUID
    project_id: uuid.UUID


class GanttEntryRead(GanttEntryBase):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    project_id: uuid.UUID

    model_config = {"from_attributes": True}
