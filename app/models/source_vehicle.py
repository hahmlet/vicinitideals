"""SourceVehicle — unified capital source preset (replaces OrgSourceVehicle + UserSourceVehicle).

A single table with a ``scope`` column (``org`` | ``user``) and ``owner_id`` pointing to
the owning organization or user respectively.  This removes the polymorphic FK pattern
where ``CapitalModule.source_vehicle_id`` could refer to either of two tables with no
database-level constraint.

Scope semantics:
- ``org``: created by org admins, visible read-only to all org members.
- ``user``: created by individual users, visible only to them.

Both scopes appear in the capital module wizard dropdown.  Once applied to a deal,
the module carries a snapshot of the vehicle config — deal data is independent of
subsequent vehicle edits.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceVehicle(Base):
    __tablename__ = "source_vehicles"
    __table_args__ = (
        UniqueConstraint("scope", "owner_id", "label", name="uq_source_vehicle_scope_owner_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Ownership
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # "org" | "user"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Identity
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    # Core type (4 mechanical types replacing 17-value FunderType)
    vehicle_type: Mapped[str] = mapped_column(String(50), nullable=False)
    equity_role: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "gp"|"lp"|NULL

    # Ordering / routing
    default_waterfall_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draw_cadence: Mapped[str] = mapped_column(String(30), nullable=False, default="monthly")

    # Debt / forgivable_loan — interest carry
    interest_rate_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    carry_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    draw_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    interest_payment_timing: Mapped[str | None] = mapped_column(String(30), nullable=True)
    day_count_convention: Mapped[str] = mapped_column(String(20), nullable=False, default="actual_360")
    io_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amort_term_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Floating rate (debt / forgivable_loan) — rate_series_ref non-null activates floating path
    rate_series_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)
    rate_spread_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    rate_reset_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Equity — preferred return / waterfall
    pref_rate_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hurdle_tiers: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # LIHTC / HTC / OZ delivery schedule (equity only)
    # [{year_offset_from_pis: int, pct: Decimal}, ...] — null = single-amount at active_from
    delivery_schedule: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Closing costs
    closing_costs_flat: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    closing_costs_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Forgivable loan
    forgiveness_trigger: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Prepayment penalty
    prepay_penalty_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Source-Use eligibility whitelist (empty = permissive / all Uses eligible)
    eligible_use_tags: Mapped[list] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default="{}",
    )

    # Legacy phase window (preserved from migration 0081 org/user_source_vehicles)
    active_phase_start: Mapped[str | None] = mapped_column(String(60), nullable=True)
    active_phase_end: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Per-deal config templates (mirror CapitalModule JSONB columns)
    source_config: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    carry_config: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    exit_config: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Developer Fee rule this preset imposes on the auto Dev Fee row.
    # Schema: app.schemas.capital.CapitalFeeTermsSchema —
    # ``{max_pct, per_unit_cap, absolute_cap, basis_exclusions[],
    #    regulated, notes}``. Empty dict = no rule. Per-deal
    # CapitalModule.fee_terms overrides on individual deals when
    # fee_terms_inherited_from_type=False.
    fee_terms: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Audit
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ---------------------------------------------------------------------------
    # Backward-compat shims for templates/code that still use old field names.
    # Remove after Phase G UI rewrite.
    # ---------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.label

    @property
    def funder_type(self) -> str:
        """Legacy funder_type string derived from vehicle_type + equity_role."""
        vt = self.vehicle_type or ""
        er = self.equity_role or ""
        if vt == "equity":
            return "common_equity" if er == "gp" else "preferred_equity"
        if vt == "debt":
            return "senior_debt"
        if vt == "forgivable_loan":
            return "soft_loan"
        if vt == "grant":
            return "grant"
        return "other"

    @property
    def org_id(self) -> "uuid.UUID | None":
        return self.owner_id if self.scope == "org" else None

    @property
    def user_id(self) -> "uuid.UUID | None":
        return self.owner_id if self.scope == "user" else None


# ---------------------------------------------------------------------------
# Backward-compat aliases — existing code that imports OrgSourceVehicle or
# UserSourceVehicle keeps working during the Phase G UI rewrite transition.
# ---------------------------------------------------------------------------
OrgSourceVehicle = SourceVehicle
UserSourceVehicle = SourceVehicle
