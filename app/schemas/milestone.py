"""Milestone Pydantic schemas for the REST/MCP milestone CRUD surface.

Milestones hang off a Project (Deal → Opportunity → Project → Milestones).
The trigger chain (``trigger_milestone_id`` + ``trigger_offset_days``) is
what lets the cashflow engine resolve real phase windows via
``Milestone.computed_start()`` — without it the engine falls back to the
legacy ``OperationalInputs.*_months`` scalars.

The v3 exporter has its own ``MilestoneImportData`` shape in
app/exporters/json_import.py (stable-id remapping semantics differ from
live CRUD), so these schemas are intentionally separate.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.milestone import MilestoneType

_EXAMPLE_MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_EXAMPLE_TRIGGER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_EXAMPLE_PROJECT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class MilestoneBase(BaseModel):
    milestone_type: MilestoneType
    # Duration in days. 0 = instantaneous; divestment is conventionally 1.
    duration_days: int = Field(default=0, ge=0)
    # Calendar pin — set on anchor milestones only (no trigger).
    target_date: date | None = None
    label: str | None = None
    # Trigger chain: start = trigger's computed end + offset_days.
    trigger_milestone_id: uuid.UUID | None = None
    trigger_offset_days: int = 0


class MilestoneCreate(MilestoneBase):
    # None → appended after the project's current max sequence_order.
    sequence_order: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "milestone_type": "construction",
                    "duration_days": 180,
                    "trigger_milestone_id": _EXAMPLE_TRIGGER_ID,
                    "trigger_offset_days": 0,
                }
            ]
        }
    )


class MilestoneUpdate(BaseModel):
    """Partial update — only provided fields are applied. Passing
    ``trigger_milestone_id: null`` explicitly detaches the milestone from
    its trigger chain (it becomes an anchor candidate)."""

    milestone_type: MilestoneType | None = None
    duration_days: int | None = Field(default=None, ge=0)
    target_date: date | None = None
    sequence_order: int | None = None
    label: str | None = None
    trigger_milestone_id: uuid.UUID | None = None
    trigger_offset_days: int | None = None


class MilestoneRead(MilestoneBase):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    sequence_order: int = 1
    # Dates resolved through the trigger chain by the router (not stored).
    # ``computed_start_date`` is None when the chain doesn't resolve (e.g.
    # the milestone's trigger was deleted and it has no target_date).
    computed_start_date: date | None = None
    computed_end_date: date | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": _EXAMPLE_MILESTONE_ID,
                    "project_id": _EXAMPLE_PROJECT_ID,
                    "milestone_type": "construction",
                    "duration_days": 180,
                    "sequence_order": 2,
                    "trigger_milestone_id": _EXAMPLE_TRIGGER_ID,
                    "trigger_offset_days": 0,
                    "computed_start_date": "2026-08-15",
                    "computed_end_date": "2027-02-11",
                }
            ]
        },
    )
