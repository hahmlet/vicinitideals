"""CapitalModule, WaterfallTier, WaterfallResult, DrawSource models (Scenario-level)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FunderType(str, enum.Enum):
    permanent_debt = "permanent_debt"    # amortizing long-term loan, no exit trigger
    senior_debt = "senior_debt"
    mezzanine_debt = "mezzanine_debt"
    bridge = "bridge"
    construction_loan = "construction_loan"
    soft_loan = "soft_loan"
    bond = "bond"
    preferred_equity = "preferred_equity"
    common_equity = "common_equity"
    owner_loan = "owner_loan"
    owner_investment = "owner_investment"
    grant = "grant"
    tax_credit = "tax_credit"
    other = "other"  # kept for backend compatibility


class WaterfallTierType(str, enum.Enum):
    debt_service = "debt_service"
    pref_return = "pref_return"
    return_of_equity = "return_of_equity"
    catch_up = "catch_up"
    irr_hurdle_split = "irr_hurdle_split"
    deferred_developer_fee = "deferred_developer_fee"
    residual = "residual"


class CapitalModule(Base):
    __tablename__ = "capital_modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    funder_type: Mapped[FunderType] = mapped_column(String(60), nullable=False)
    stack_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    carry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exit_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active_phase_start: Mapped[str | None] = mapped_column(String(60), nullable=True)
    active_phase_end: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="capital_modules"
    )
    waterfall_tiers: Mapped[list["WaterfallTier"]] = relationship(
        "WaterfallTier", back_populates="capital_module"
    )
    waterfall_results: Mapped[list["WaterfallResult"]] = relationship(
        "WaterfallResult", back_populates="capital_module"
    )
    draw_source: Mapped["DrawSource | None"] = relationship(
        "DrawSource", back_populates="capital_module", uselist=False
    )


class WaterfallTier(Base):
    __tablename__ = "waterfall_tiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    capital_module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_modules.id"), nullable=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_type: Mapped[WaterfallTierType] = mapped_column(String(60), nullable=False)
    irr_hurdle_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lp_split_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    gp_split_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # DDF-specific: cap how much of distributable cash goes to DDF repayment per period
    max_pct_of_distributable: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # DDF-specific: optional accrual rate on unpaid balance
    interest_rate_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="waterfall_tiers"
    )
    capital_module: Mapped["CapitalModule | None"] = relationship(
        "CapitalModule", back_populates="waterfall_tiers"
    )
    waterfall_results: Mapped[list["WaterfallResult"]] = relationship(
        "WaterfallResult", back_populates="tier"
    )


class WaterfallResult(Base):
    __tablename__ = "waterfall_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waterfall_tiers.id"), nullable=False
    )
    capital_module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_modules.id"), nullable=False
    )
    cash_distributed: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    cumulative_distributed: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    party_irr_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="waterfall_results"
    )
    tier: Mapped["WaterfallTier"] = relationship(
        "WaterfallTier", back_populates="waterfall_results"
    )
    capital_module: Mapped["CapitalModule"] = relationship(
        "CapitalModule", back_populates="waterfall_results"
    )


class DrawSource(Base):
    """A funding source in the draw schedule — equity or debt, tied to deal milestones.

    Sources are ordered (sort_order) and form a Gantt: each covers a window from
    active_from_milestone to active_to_milestone.  The engine auto-sizes draws every
    draw_every_n_months to cover Uses + carry (self-referential formula for debt).
    """

    __tablename__ = "draw_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # "equity" or "debt"
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="equity")
    draw_every_n_months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    annual_interest_rate: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    active_from_milestone: Mapped[str] = mapped_column(String(60), nullable=False)
    active_to_milestone: Mapped[str] = mapped_column(String(60), nullable=False)
    # Offset in days from the milestone date (e.g. "Construction + 30 days")
    active_from_offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    active_to_offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # None = auto-sized to total drawn
    total_commitment: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # Denormalized from CapitalModule for display without join
    funder_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Link back to the CapitalModule this was created from (wizard saves both atomically)
    capital_module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capital_modules.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="draw_sources"
    )
    capital_module: Mapped["CapitalModule | None"] = relationship(
        "CapitalModule", back_populates="draw_source"
    )
