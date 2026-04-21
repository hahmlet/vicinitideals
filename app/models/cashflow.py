"""CashFlow, CashFlowLineItem, OperationalOutputs models (Scenario-level)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PeriodType(str, enum.Enum):
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


class LineItemCategory(str, enum.Enum):
    income = "income"
    expense = "expense"
    debt_service = "debt_service"
    capex_reserve = "capex_reserve"
    capital_event = "capital_event"


class CashFlow(Base):
    __tablename__ = "cash_flows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    # Per-project output routing (added in migration 0050). Nullable during
    # the backfill window; the engine populates it on every new row so the
    # Underwriting rollup can sum per-project CF rows.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    period_type: Mapped[PeriodType] = mapped_column(String(60), nullable=False)
    gross_revenue: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    vacancy_loss: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    effective_gross_income: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    operating_expenses: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    capex_reserve: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    noi: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    debt_service: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    net_cash_flow: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    cumulative_cash_flow: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="cash_flows"
    )


class CashFlowLineItem(Base):
    __tablename__ = "cash_flow_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    income_stream_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("income_streams.id"), nullable=True
    )
    category: Mapped[LineItemCategory] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    base_amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    adjustments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    net_amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="cash_flow_line_items"
    )
    income_stream: Mapped["IncomeStream | None"] = relationship(  # type: ignore[name-defined]
        "IncomeStream", back_populates="cash_flow_line_items"
    )


class OperationalOutputs(Base):
    __tablename__ = "operational_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id"),
        unique=True,
        nullable=False,
    )
    # Per-project output routing (added in migration 0050). Still nullable
    # because the unique-on-scenario_id constraint above enforces one row per
    # scenario today; Phase 2b will swap that for (scenario_id, project_id)
    # unique so per-project output rows can coexist.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    total_project_cost: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    equity_required: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_timeline_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    noi_stabilized: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    cap_rate_on_cost_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    dscr: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    project_irr_levered: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    project_irr_unlevered: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    debt_yield_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # 5x5 sensitivity matrix: {param_x, param_y, values: [[...]]}
    sensitivity_matrix: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="operational_outputs"
    )
