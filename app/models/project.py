"""Project (post-acquisition dev effort) and PermitStub models.

Entity hierarchy (post-refactor):
    Opportunity  — unified investment target (was ScrapedListing); lives in
                   app/models/opportunity.py
    Project      — one financial scenario slice inside a Deal; references one
                   Opportunity for lineage (never written back to).

Physical attributes (sqft, units, year_built) come from the Opportunity.
unit_mix is JSONB on Project — deep-copied from Opportunity at creation.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Re-export enums from opportunity.py so existing imports of these from project.py
# continue to work.
from app.models.opportunity import (  # noqa: F401
    OpportunityCategory,
    OpportunitySource,
    OpportunityStatus,
    ProjectCategory,
    ProjectSource,
    ProjectStatus,
)


class Project(Base):
    """Post-acquisition development effort (one slice of a Deal).

    References one Opportunity (the property being acquired) for lineage.
    Physical data deep-copied at creation; edits here never write back to
    the Opportunity.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Project")
    proposed_use: Mapped[str | None] = mapped_column(String(60), nullable=True)
    acquisition_price: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    # JSONB unit mix — deep-copied from opportunity at project creation.
    # Shape: list of {label, beds, baths, sqft, rent_monthly, unit_count, notes}
    unit_mix: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Gating flag — must approve timeline before other modules unlock
    timeline_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="projects"
    )
    opportunity: Mapped["Opportunity | None"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="dev_projects"
    )
    parcel: Mapped["Parcel | None"] = relationship(  # type: ignore[name-defined]
        "Parcel", foreign_keys=[parcel_id]
    )
    use_lines: Mapped[list["UseLine"]] = relationship(  # type: ignore[name-defined]
        "UseLine", back_populates="project"
    )
    income_streams: Mapped[list["IncomeStream"]] = relationship(  # type: ignore[name-defined]
        "IncomeStream", back_populates="project"
    )
    expense_lines: Mapped[list["OperatingExpenseLine"]] = relationship(  # type: ignore[name-defined]
        "OperatingExpenseLine", back_populates="project"
    )
    operational_inputs: Mapped["OperationalInputs | None"] = relationship(  # type: ignore[name-defined]
        "OperationalInputs", back_populates="project", uselist=False
    )
    milestones: Mapped[list["Milestone"]] = relationship(  # type: ignore[name-defined]
        "Milestone",
        primaryjoin="and_(Milestone.project_id == Project.id, "
                    "Milestone.project_id != None)",
        back_populates="project",
    )
    capital_module_terms: Mapped[list["CapitalModuleProject"]] = relationship(  # type: ignore[name-defined]
        "CapitalModuleProject",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    anchor: Mapped["ProjectAnchor | None"] = relationship(
        "ProjectAnchor",
        back_populates="project",
        foreign_keys="ProjectAnchor.project_id",
        cascade="all, delete-orphan",
        uselist=False,
    )


class PermitStub(Base):
    __tablename__ = "permit_stubs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    permit_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permit_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="permit_stubs"
    )


class ProjectAnchor(Base):
    """Cross-project timeline coupling.

    Presence means the owning Project's first-milestone date resolves relative to
    anchor_project's anchor milestone plus offset. Added in migration 0048.
    """

    __tablename__ = "project_anchors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    anchor_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    anchor_milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("milestones.id", ondelete="SET NULL"),
        nullable=True,
    )
    offset_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    offset_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(
        "Project", back_populates="anchor", foreign_keys=[project_id],
    )
    anchor_project: Mapped["Project"] = relationship(
        "Project", foreign_keys=[anchor_project_id],
    )
    anchor_milestone: Mapped["Milestone | None"] = relationship(  # type: ignore[name-defined]
        "Milestone", foreign_keys=[anchor_milestone_id],
    )


from app.models.capital import CapitalModuleProject  # noqa: E402,F401
from app.models.opportunity import Opportunity  # noqa: E402,F401
