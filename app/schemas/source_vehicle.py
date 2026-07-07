"""Pydantic v2 schemas for the unified SourceVehicle model."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vocab import (
    CarryTypeLiteral,
    DayCountLiteral,
    EquityRoleLiteral,
    VehicleTypeLiteral,
)


class HurdleTier(BaseModel):
    irr_hurdle_pct: Decimal
    lp_split_pct: Decimal
    gp_split_pct: Decimal
    description: str = ""


class VehicleSourceConfig(BaseModel):
    """Mirrors CapitalSourceSchema shape for vehicle-level defaults."""

    model_config = ConfigDict(extra="allow")

    amount: Decimal | None = None
    interest_rate_pct: float | None = None
    ltv_pct: float | None = None
    dscr_min: float | None = None
    hold_term_years: int | None = None
    prepay_penalty_pct: float | None = None


class VehicleCarryConfig(BaseModel):
    """Mirrors CapitalCarrySchema shape for vehicle-level defaults."""

    model_config = ConfigDict(extra="allow")

    carry_type: CarryTypeLiteral | None = None
    io_rate_pct: float | None = None
    io_period_months: int | None = None
    amort_term_years: int | None = None
    day_count: DayCountLiteral | None = None
    phases: list[dict] | None = None


class VehicleExitConfig(BaseModel):
    """Mirrors CapitalExitSchema shape for vehicle-level defaults."""

    model_config = ConfigDict(extra="allow")

    exit_type: str | None = None
    trigger: str | None = None


class SourceVehicleCreate(BaseModel):
    scope: Literal["org", "user"]
    owner_id: uuid.UUID
    label: str = Field(..., max_length=200)
    vehicle_type: VehicleTypeLiteral
    equity_role: EquityRoleLiteral | None = None
    default_waterfall_position: int = 0
    draw_cadence: Literal[
        "monthly", "bi_monthly", "quarterly", "lump_at_trigger", "residual_gap_filler"
    ] = "monthly"
    # Debt / forgivable_loan fields
    interest_rate_pct: Decimal | None = None
    carry_type: CarryTypeLiteral | None = None
    interest_payment_timing: Literal[
        "monthly_arrears", "quarterly_arrears", "at_maturity", "accrue_to_balance"
    ] | None = None
    day_count_convention: DayCountLiteral = "actual_360"
    io_period_months: int | None = None
    amort_term_years: int | None = None
    # Floating rate fields (debt / forgivable_loan)
    rate_series_ref: str | None = None
    rate_spread_pct: Decimal | None = None
    rate_reset_frequency: Literal["monthly", "quarterly", "annually"] | None = None
    # Equity fields
    pref_rate_pct: Decimal | None = None
    hurdle_tiers: list[HurdleTier] | None = None
    # LIHTC / tax credit delivery schedule
    # [{year_offset_from_pis: int, pct: Decimal}, ...] — null = single-amount at active_from
    delivery_schedule: list[dict] | None = None
    # Closing costs
    closing_costs_flat: Decimal = Decimal("0")
    closing_costs_pct: Decimal = Decimal("0")
    # Forgivable loan
    forgiveness_trigger: str | None = None
    prepay_penalty_pct: Decimal = Decimal("0")
    # Source-Use eligibility whitelist (empty = permissive / all eligible)
    eligible_use_tags: list[str] = Field(default_factory=list)
    # Phase window (preserved from legacy vehicles)
    active_phase_start: str | None = None
    active_phase_end: str | None = None
    # Per-deal config templates (mirrors CapitalModule JSONB columns)
    source_config: dict | None = None
    carry_config: dict | None = None
    exit_config: dict | None = None


class SourceVehicleUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    vehicle_type: VehicleTypeLiteral | None = None
    equity_role: EquityRoleLiteral | None = None
    default_waterfall_position: int | None = None
    draw_cadence: Literal[
        "monthly", "bi_monthly", "quarterly", "lump_at_trigger", "residual_gap_filler"
    ] | None = None
    interest_rate_pct: Decimal | None = None
    carry_type: CarryTypeLiteral | None = None
    interest_payment_timing: Literal[
        "monthly_arrears", "quarterly_arrears", "at_maturity", "accrue_to_balance"
    ] | None = None
    day_count_convention: DayCountLiteral | None = None
    io_period_months: int | None = None
    amort_term_years: int | None = None
    rate_series_ref: str | None = None
    rate_spread_pct: Decimal | None = None
    rate_reset_frequency: Literal["monthly", "quarterly", "annually"] | None = None
    pref_rate_pct: Decimal | None = None
    hurdle_tiers: list[HurdleTier] | None = None
    delivery_schedule: list[dict] | None = None
    closing_costs_flat: Decimal | None = None
    closing_costs_pct: Decimal | None = None
    forgiveness_trigger: str | None = None
    prepay_penalty_pct: Decimal | None = None
    eligible_use_tags: list[str] | None = None
    active_phase_start: str | None = None
    active_phase_end: str | None = None
    source_config: dict | None = None
    carry_config: dict | None = None
    exit_config: dict | None = None


class SourceVehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: uuid.UUID
    scope: str
    owner_id: uuid.UUID
    label: str
    vehicle_type: str
    equity_role: str | None = None
    default_waterfall_position: int
    draw_cadence: str
    interest_rate_pct: Decimal | None = None
    carry_type: str | None = None
    interest_payment_timing: str | None = None
    day_count_convention: str
    io_period_months: int | None = None
    amort_term_years: int | None = None
    rate_series_ref: str | None = None
    rate_spread_pct: Decimal | None = None
    rate_reset_frequency: str | None = None
    pref_rate_pct: Decimal | None = None
    hurdle_tiers: list[dict] | None = None
    delivery_schedule: list[dict] | None = None
    closing_costs_flat: Decimal
    closing_costs_pct: Decimal
    forgiveness_trigger: str | None = None
    prepay_penalty_pct: Decimal
    eligible_use_tags: list[str]
    active_phase_start: str | None = None
    active_phase_end: str | None = None
    source_config: dict | None = None
    carry_config: dict | None = None
    exit_config: dict | None = None
