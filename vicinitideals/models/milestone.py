"""Milestone model — duration-based timeline for Opportunities and Projects.

Pre-close milestones (offer_made, under_contract, close) → Opportunity
Post-close milestones (pre_development, construction, operation_lease_up,
                       operation_stabilized, divestment)  → Project

Exactly one of opportunity_id or project_id must be set (enforced by DB CHECK
constraint in migration 0011).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vicinitideals.models.base import Base


class MilestoneType(str, enum.Enum):
    # Pre-close (Opportunity-level)
    offer_made = "offer_made"
    under_contract = "under_contract"
    close = "close"
    # Post-close (Project-level)
    pre_development = "pre_development"
    construction = "construction"
    operation_lease_up = "operation_lease_up"
    operation_stabilized = "operation_stabilized"
    divestment = "divestment"


# Default durations (days) per milestone type and deal type
# Used when a new Project is created to pre-populate the milestone list.
DEFAULT_DURATIONS: dict[str, dict[str, int]] = {
    "acquisition_minor_reno": {
        "offer_made": 14,
        "under_contract": 30,
        "close": 45,
        "construction": 90,
        "operation_stabilized": 1825,  # 5 years
        "divestment": 30,
    },
    "acquisition_major_reno": {
        "offer_made": 14,
        "under_contract": 30,
        "close": 45,
        "pre_development": 90,
        "construction": 180,
        "operation_lease_up": 120,
        "operation_stabilized": 1825,
        "divestment": 30,
    },
    "acquisition_conversion": {
        "offer_made": 14,
        "under_contract": 30,
        "close": 45,
        "pre_development": 90,
        "construction": 180,
        "operation_lease_up": 120,
        "operation_stabilized": 1825,
        "divestment": 30,
    },
    "new_construction": {
        "offer_made": 14,
        "under_contract": 30,
        "close": 45,
        "pre_development": 180,
        "construction": 365,
        "operation_lease_up": 120,
        "operation_stabilized": 1825,
        "divestment": 30,
    },
}


class Milestone(Base):
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint(
            "(opportunity_id IS NOT NULL AND project_id IS NULL) OR "
            "(opportunity_id IS NULL AND project_id IS NOT NULL)",
            name="ck_milestones_single_parent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Trigger-based positioning: start = trigger.end_date + offset_days
    # If NULL, milestone is an anchor (uses target_date directly)
    trigger_milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("milestones.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    milestone_type: Mapped[MilestoneType] = mapped_column(String(60), nullable=False)
    # Duration from previous milestone start (days). 0 = same day as previous.
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional calendar pin — overrides duration-based positioning
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 1-based ordering within the sequence
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Human-readable override label
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def computed_start(self, milestone_map: "dict[uuid.UUID, Milestone] | None" = None) -> "date | None":
        """Resolve start date, following trigger chain. milestone_map avoids repeated DB hits."""
        if self.trigger_milestone_id is None:
            return self.target_date
        if milestone_map is None:
            return None  # can't resolve without the map
        trigger = milestone_map.get(self.trigger_milestone_id)
        if trigger is None:
            return None
        trigger_end = trigger.computed_end(milestone_map)
        if trigger_end is None:
            return None
        return trigger_end + timedelta(days=self.trigger_offset_days)

    def computed_end(self, milestone_map: "dict[uuid.UUID, Milestone] | None" = None) -> "date | None":
        start = self.computed_start(milestone_map)
        if start and self.duration_days:
            return start + timedelta(days=self.duration_days)
        return None

    @property
    def end_date(self) -> "date | None":
        """Shortcut for standalone use (anchor milestones only — no trigger chain)."""
        if self.target_date and self.duration_days:
            return self.target_date + timedelta(days=self.duration_days)
        return None

    @property
    def is_anchor(self) -> bool:
        return self.trigger_milestone_id is None

    # Relationships
    opportunity: Mapped["Opportunity | None"] = relationship(  # type: ignore[name-defined]
        "Opportunity",
        foreign_keys=[opportunity_id],
        back_populates="milestones",
    )
    project: Mapped["Project | None"] = relationship(  # type: ignore[name-defined]
        "Project",
        foreign_keys=[project_id],
        back_populates="milestones",
    )
