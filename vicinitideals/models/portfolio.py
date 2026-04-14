"""Portfolio, PortfolioProject, GanttEntry models."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vicinitideals.models.base import Base


class GanttPhase(str, enum.Enum):
    acquisition = "acquisition"
    hold = "hold"
    pre_construction = "pre_construction"
    minor_renovation = "minor_renovation"
    major_renovation = "major_renovation"
    conversion = "conversion"
    construction = "construction"
    lease_up = "lease_up"
    stabilized = "stabilized"
    exit = "exit"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization", back_populates="portfolios"
    )
    portfolio_projects: Mapped[list["PortfolioProject"]] = relationship(
        "PortfolioProject", back_populates="portfolio"
    )
    gantt_entries: Mapped[list["GanttEntry"]] = relationship(
        "GanttEntry", back_populates="portfolio"
    )


class PortfolioProject(Base):
    __tablename__ = "portfolio_projects"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id"),
        primary_key=True,
    )
    # References Opportunity (was Project before rename)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id"),
        primary_key=True,
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    capital_contribution: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="portfolio_projects"
    )
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="portfolio_projects"
    )
    scenario: Mapped["Scenario | None"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="portfolio_scenarios"
    )


class GanttEntry(Base):
    __tablename__ = "gantt_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    # References Opportunity (was Project before rename)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    phase: Mapped[GanttPhase] = mapped_column(String(60), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="gantt_entries"
    )
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="gantt_entries"
    )
