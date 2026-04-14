"""Sensitivity (sensitivity/scenario analysis sweep), SensitivityResult models.

Was previously named Scenario/ScenarioResult.  Renamed to free up the `scenarios`
table name for the new Deal→Scenario financial plan entity in deal.py.

Backward-compat aliases are kept so existing code importing Scenario/ScenarioResult
continues to work without immediate churn.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SensitivityStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


# Backward-compat alias
ScenarioStatus = SensitivityStatus


class Sensitivity(Base):
    """A sensitivity / scenario-analysis sweep — varies one input across a range.

    Previously named Scenario.  The DealModel-level financial plan is now also
    called a Scenario (in deal.py), so this class was renamed to avoid collision.
    """

    __tablename__ = "sensitivities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # References Opportunity (was Project before rename)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    variable: Mapped[str] = mapped_column(String(255), nullable=False)
    range_min: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False)
    range_max: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False)
    range_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[SensitivityStatus] = mapped_column(
        String(30), nullable=False, default=SensitivityStatus.pending
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    model_version_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="sensitivities"
    )
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="sensitivities"
    )
    results: Mapped[list["SensitivityResult"]] = relationship(
        "SensitivityResult", back_populates="sensitivity", passive_deletes=True
    )


# Backward-compat alias — old code importing Scenario still works
Scenario = Sensitivity


class SensitivityResult(Base):
    __tablename__ = "sensitivity_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sensitivity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sensitivities.id"), nullable=False
    )
    run_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    variable_value: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False)
    project_irr_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lp_irr_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    gp_irr_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    equity_multiple: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_on_cash_year1_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Relationships
    sensitivity: Mapped["Sensitivity"] = relationship("Sensitivity", back_populates="results")


# Backward-compat alias
ScenarioResult = SensitivityResult
