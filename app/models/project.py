"""Opportunity, Project (post-acquisition), and PermitStub models.

Entity hierarchy:
  Opportunity  — the investment target / purchase transaction (was "Project")
  Project      — post-acquisition development effort (new entity, lives inside a Deal)

Both are top-level.  A Deal has one or more Projects; each Project references one Opportunity.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class OpportunityStatus(str, enum.Enum):
    hypothetical = "hypothetical"
    active = "active"
    archived = "archived"


# Backward-compat alias
ProjectStatus = OpportunityStatus


class OpportunityCategory(str, enum.Enum):
    proposed = "proposed"
    historical = "historical"


ProjectCategory = OpportunityCategory


class OpportunitySource(str, enum.Enum):
    loopnet = "loopnet"
    crexi = "crexi"
    user_generated = "user_generated"
    manual = "manual"


ProjectSource = OpportunitySource


class Opportunity(Base):
    """An investment target — one purchase transaction (was 'Project')."""

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OpportunityStatus] = mapped_column(
        String(50), nullable=False, default=OpportunityStatus.hypothetical
    )
    project_category: Mapped[OpportunityCategory] = mapped_column(
        String(50), nullable=False, default=OpportunityCategory.proposed
    )
    source: Mapped[OpportunitySource | None] = mapped_column(String(50), nullable=True)
    # scraped | manual — differentiates listing-sourced vs user-created opportunities
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="manual"
    )
    # Promotion audit: "auto" (matched a ruleset) | "manual" (user clicked Promote) | None (not listing-sourced)
    promotion_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Which SavedSearchCriteria triggered auto-promotion (null for manual or user-created)
    promotion_ruleset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_search_criteria.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    multi_parcel_dismissed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization", back_populates="opportunities"
    )
    promotion_ruleset: Mapped["SavedSearchCriteria | None"] = relationship(  # type: ignore[name-defined]
        "SavedSearchCriteria",
        foreign_keys=[promotion_ruleset_id],
    )
    project_visibilities: Mapped[list["ProjectVisibility"]] = relationship(  # type: ignore[name-defined]
        "ProjectVisibility", back_populates="opportunity"
    )
    project_parcels: Mapped[list["ProjectParcel"]] = relationship(  # type: ignore[name-defined]
        "ProjectParcel", back_populates="opportunity"
    )
    parcel_transformations: Mapped[list["ParcelTransformation"]] = relationship(  # type: ignore[name-defined]
        "ParcelTransformation", back_populates="opportunity"
    )
    permit_stubs: Mapped[list["PermitStub"]] = relationship(
        "PermitStub", back_populates="opportunity"
    )
    scraped_listings: Mapped[list["ScrapedListing"]] = relationship(  # type: ignore[name-defined]
        "ScrapedListing", back_populates="linked_opportunity"
    )
    # Projects that reference this Opportunity (post-acquisition dev efforts)
    dev_projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="opportunity"
    )
    # Pre-close milestones (Offer Made, Under Contract, Close)
    milestones: Mapped[list["Milestone"]] = relationship(  # type: ignore[name-defined]
        "Milestone",
        primaryjoin="and_(Milestone.opportunity_id == Opportunity.id, "
                    "Milestone.opportunity_id != None)",
        back_populates="opportunity",
    )
    deal_opportunities: Mapped[list["DealOpportunity"]] = relationship(  # type: ignore[name-defined]
        "DealOpportunity", back_populates="opportunity"
    )
    opportunity_buildings: Mapped[list["OpportunityBuilding"]] = relationship(  # type: ignore[name-defined]
        "OpportunityBuilding", back_populates="opportunity", order_by="OpportunityBuilding.sort_order"
    )
    sensitivities: Mapped[list["Sensitivity"]] = relationship(  # type: ignore[name-defined]
        "Sensitivity", back_populates="opportunity"
    )
    portfolio_projects: Mapped[list["PortfolioProject"]] = relationship(  # type: ignore[name-defined]
        "PortfolioProject", back_populates="opportunity"
    )
    gantt_entries: Mapped[list["GanttEntry"]] = relationship(  # type: ignore[name-defined]
        "GanttEntry", back_populates="opportunity"
    )


class Project(Base):
    """Post-acquisition development effort (new entity).

    Lives inside a Deal; references one Opportunity (the purchase target).
    The granularity of a Project is user-chosen — one Opportunity's buildings
    may be split across multiple Projects.
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
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Project")
    deal_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # Gating flag — must approve timeline before other modules unlock
    timeline_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="projects"
    )
    opportunity: Mapped["Opportunity | None"] = relationship(
        "Opportunity", back_populates="dev_projects"
    )
    # Line-item tables that belong to a Project (not the Deal)
    use_lines: Mapped[list["UseLine"]] = relationship(  # type: ignore[name-defined]
        "UseLine", back_populates="project"
    )
    income_streams: Mapped[list["IncomeStream"]] = relationship(  # type: ignore[name-defined]
        "IncomeStream", back_populates="project"
    )
    expense_lines: Mapped[list["OperatingExpenseLine"]] = relationship(  # type: ignore[name-defined]
        "OperatingExpenseLine", back_populates="project"
    )
    unit_mix: Mapped[list["UnitMix"]] = relationship(  # type: ignore[name-defined]
        "UnitMix", back_populates="project", cascade="all, delete-orphan"
    )
    operational_inputs: Mapped["OperationalInputs | None"] = relationship(  # type: ignore[name-defined]
        "OperationalInputs", back_populates="project", uselist=False
    )
    # Post-close milestones (Pre-Dev, Construction, Lease-Up, Stabilized, Divestment)
    milestones: Mapped[list["Milestone"]] = relationship(  # type: ignore[name-defined]
        "Milestone",
        primaryjoin="and_(Milestone.project_id == Project.id, "
                    "Milestone.project_id != None)",
        back_populates="project",
    )
    # Per-project building and parcel assignments (which buildings/parcels scope this project)
    building_assignments: Mapped[list["ProjectBuildingAssignment"]] = relationship(
        "ProjectBuildingAssignment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectBuildingAssignment.sort_order",
    )
    parcel_assignments: Mapped[list["ProjectParcelAssignment"]] = relationship(
        "ProjectParcelAssignment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectParcelAssignment.sort_order",
    )


class ProjectBuildingAssignment(Base):
    """Explicit assignment of a Building to a specific Project within a Deal.

    A Building can be assigned to multiple Projects (for variant modeling).
    Distinct from OpportunityBuilding, which tracks all buildings at the Opportunity level.
    """

    __tablename__ = "project_building_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)

    project: Mapped["Project"] = relationship("Project", back_populates="building_assignments")
    building: Mapped["Building"] = relationship("Building")  # type: ignore[name-defined]


class ProjectParcelAssignment(Base):
    """Explicit assignment of a Parcel to a specific Project within a Deal.

    A Parcel can be assigned to multiple Projects (for variant modeling).
    Distinct from ProjectParcel, which tracks parcel transformations at the Opportunity level.
    """

    __tablename__ = "project_parcel_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)

    project: Mapped["Project"] = relationship("Project", back_populates="parcel_assignments")
    parcel: Mapped["Parcel"] = relationship("Parcel")  # type: ignore[name-defined]


class PermitStub(Base):
    __tablename__ = "permit_stubs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # References Opportunity (was Project before rename)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    permit_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permit_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    opportunity: Mapped["Opportunity"] = relationship(
        "Opportunity", back_populates="permit_stubs"
    )


from app.models.scraped_listing import ScrapedListing  # noqa: E402,F401
