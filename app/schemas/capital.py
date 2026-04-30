"""
Capital stack Pydantic schemas.

These are stored as JSONB in CapitalModule.source / .carry / .exit_terms columns.
They are also used as standalone validation schemas for the capital stack engine.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_EXAMPLE_MODEL_ID = "44444444-4444-4444-4444-444444444444"
_EXAMPLE_CAPITAL_MODULE_ID = "99999999-9999-9999-9999-999999999999"
_EXAMPLE_WATERFALL_TIER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_EXAMPLE_CREATED_AT = "2026-04-03T12:00:00Z"


def _example_config(example: dict[str, object], *, from_attributes: bool = False) -> ConfigDict:
    config: dict[str, object] = {"json_schema_extra": {"examples": [example]}}
    if from_attributes:
        config["from_attributes"] = True
    return ConfigDict(**config)


# ---------------------------------------------------------------------------
# Sub-schemas stored inside CapitalSourceSchema
# ---------------------------------------------------------------------------

class CapitalDraw(BaseModel):
    label: str
    amount: Decimal
    date: date
    io_rate_pct: float


# ---------------------------------------------------------------------------
# Column-level JSONB schemas (map to CapitalModule ORM columns)
# ---------------------------------------------------------------------------

class CapitalSourceSchema(BaseModel):
    """Source (principal) config for a CapitalModule.

    ``extra="allow"`` preserves engine-written keys that aren't declared
    here: ``auto_size``, ``is_bridge``, ``construction_retirement``,
    ``ltv_pct``, ``sizing_approach``, ``fixed_amount``, etc.  These live
    in the JSONB column and must survive a JSON export/import round-trip.
    """

    model_config = ConfigDict(extra="allow")

    amount: Decimal | None = None
    pct_of_total_cost: float | None = None
    interest_rate_pct: float | None = None
    funding_date_trigger: str = ""
    draws: list[CapitalDraw] = []
    notes: str = ""
    # ── Phase B (multi-debt path) fields ─────────────────────────────────
    auto_size: bool | None = None
    is_bridge: bool | None = None
    construction_retirement: str | None = None
    ltv_pct: float | None = None
    sizing_approach: str | None = None
    fixed_amount: float | None = None
    # Refi: cap rate override for property valuation at refi (defaults to going-in cap)
    refi_cap_rate_pct: float | None = None
    # Prepay penalty as % of outstanding balloon balance at payoff
    prepay_penalty_pct: float | None = None
    # Modeled hold period in years for the loan. Required when the parent
    # CapitalModule has funder_type == "permanent_debt" — the cashflow
    # engine reads this as the loan's balloon point and the deal-level
    # horizon resolver takes MAX across all perm-debt modules.
    hold_term_years: int | None = None
    # Minimum DSCR floor for sizing. Used by the DSCR-capped auto-sizer when
    # this module is the perm loan being sized. Falls back to 1.20 if unset.
    dscr_min: float | None = None


class CapitalCarrySchema(BaseModel):
    """Carry config for a CapitalModule.

    Supports two shapes:

    1. **Flat** (single carry across all phases):
       ``{"carry_type": "interest_reserve", "io_rate_pct": 6.5, ...}``

    2. **Phased** (different carry per life-cycle phase, e.g. io_then_pi):
       ``{"phases": [
            {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": 6},
            {"name": "operation",    "carry_type": "pi", "amort_term_years": 30, "io_rate_pct": 5},
          ]}``

    Both `carry_type` and `phases` are optional at the top level so either
    shape validates cleanly.  ``extra="allow"`` preserves any future
    engine-specific keys (draw_schedule, interest_accrual_method, etc.)
    on round-trip through the JSON exporter so deals survive Phase 1 /
    Phase 2 feature additions without schema churn.
    """

    model_config = ConfigDict(extra="allow")

    carry_type: Literal[
        "io_only",
        "interest_reserve",
        "capitalized_interest",
        "accruing",
        "pi",
        "none",
    ] | None = None
    io_period_months: int | None = None
    io_to_pi_trigger: str | None = None
    payment_frequency: Literal["monthly", "quarterly", "annual", "at_exit"] = "monthly"
    capitalized: bool = False

    # ── Phase 1 (carry type rewrite) ─────────────────────────────────────
    # Annual interest rate for io_only / interest_reserve / capitalized_interest
    # / pi construction phases.  The engine reads this from both the flat and
    # phased shapes.  Prior to this field being declared on the schema,
    # Pydantic silently dropped it on serialization and Phase 1 exports lost
    # rate data.
    io_rate_pct: float | None = None

    # Amortization term in years for pi carry types.  Also used by the
    # operation phase of io_then_pi.
    amort_term_years: int | None = None

    # Phased carry (io_then_pi etc.).  Each phase is a dict with at least
    # {name, carry_type} plus optional {io_rate_pct, amort_term_years, ...}.
    # Kept as list[dict] rather than a strict sub-model so we don't silently
    # drop keys the engine adds in future rewrites.
    phases: list[dict] | None = None


class CapitalExitSchema(BaseModel):
    exit_type: Literal[
        "full_payoff", "tranche_payoff", "equity_conversion", "profit_share", "forgiven"
    ]
    trigger: str
    tranches: list[dict] | None = None
    equity_conversion_pct: float | None = None
    profit_share_pct: float | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# CapitalModule CRUD schemas
# ---------------------------------------------------------------------------

class CapitalModuleBase(BaseModel):
    label: str
    funder_type: str
    stack_position: int = 0
    source: CapitalSourceSchema | None = None
    carry: CapitalCarrySchema | None = None
    exit_terms: CapitalExitSchema | None = None
    active_phase_start: str | None = None
    active_phase_end: str | None = None

    @model_validator(mode="after")
    def _require_perm_debt_hold_term(self) -> "CapitalModuleBase":
        ft = (self.funder_type or "").replace("FunderType.", "")
        if ft == "permanent_debt":
            hold = self.source.hold_term_years if self.source is not None else None
            if hold is None or hold <= 0:
                raise ValueError(
                    "permanent_debt CapitalModule requires source.hold_term_years > 0"
                )
        return self


class CapitalModuleCreate(CapitalModuleBase):
    scenario_id: uuid.UUID

    model_config = _example_config(
        {
            "scenario_id": _EXAMPLE_MODEL_ID,
            "label": "Senior Loan",
            "funder_type": "debt",
            "stack_position": 1,
            "source": {
                "amount": "850000",
                "interest_rate_pct": 6.5,
                "funding_date_trigger": "construction_start",
            },
            "carry": {
                "carry_type": "io_only",
                "io_period_months": 12,
                "payment_frequency": "monthly",
                "capitalized": False,
            },
            "exit_terms": {
                "exit_type": "full_payoff",
                "trigger": "sale",
                "notes": "Pay off at disposition",
            },
            "active_phase_start": "acquisition",
            "active_phase_end": "exit",
        }
    )


class CapitalModuleUpdate(BaseModel):
    label: str | None = None
    funder_type: str | None = None
    stack_position: int | None = None
    source: CapitalSourceSchema | None = None
    carry: CapitalCarrySchema | None = None
    exit_terms: CapitalExitSchema | None = None
    active_phase_start: str | None = None
    active_phase_end: str | None = None

    model_config = _example_config(
        {
            "label": "Senior Loan - Requoted",
            "source": {"amount": "900000", "interest_rate_pct": 6.1},
            "carry": {"carry_type": "pi", "payment_frequency": "monthly", "capitalized": False},
        }
    )


class CapitalModuleRead(CapitalModuleBase):
    id: uuid.UUID
    scenario_id: uuid.UUID
    created_at: datetime

    model_config = _example_config(
        {
            "id": _EXAMPLE_CAPITAL_MODULE_ID,
            "scenario_id": _EXAMPLE_MODEL_ID,
            "label": "Senior Loan",
            "funder_type": "debt",
            "stack_position": 1,
            "source": {"amount": "850000", "interest_rate_pct": 6.5},
            "carry": {"carry_type": "io_only", "payment_frequency": "monthly", "capitalized": False},
            "exit_terms": {"exit_type": "full_payoff", "trigger": "sale"},
            "active_phase_start": "acquisition",
            "active_phase_end": "exit",
            "created_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# WaterfallTier CRUD schemas
# ---------------------------------------------------------------------------

class WaterfallTierBase(BaseModel):
    priority: int
    tier_type: str
    irr_hurdle_pct: Decimal | None = None
    lp_split_pct: Decimal = Decimal("0")
    gp_split_pct: Decimal = Decimal("0")
    description: str | None = None
    capital_module_id: uuid.UUID | None = None
    # DDF-specific fields (ignored for non-DDF tier types)
    max_pct_of_distributable: Decimal | None = None
    interest_rate_pct: Decimal | None = None


class WaterfallTierCreate(WaterfallTierBase):
    scenario_id: uuid.UUID

    model_config = _example_config(
        {
            "scenario_id": _EXAMPLE_MODEL_ID,
            "capital_module_id": _EXAMPLE_CAPITAL_MODULE_ID,
            "priority": 1,
            "tier_type": "return_of_equity",
            "irr_hurdle_pct": "8.0",
            "lp_split_pct": "90",
            "gp_split_pct": "10",
            "description": "Return sponsor equity first",
        }
    )


class WaterfallTierUpdate(BaseModel):
    priority: int | None = None
    tier_type: str | None = None
    irr_hurdle_pct: Decimal | None = None
    lp_split_pct: Decimal | None = None
    gp_split_pct: Decimal | None = None
    description: str | None = None
    capital_module_id: uuid.UUID | None = None
    max_pct_of_distributable: Decimal | None = None
    interest_rate_pct: Decimal | None = None

    model_config = _example_config(
        {
            "irr_hurdle_pct": "10.0",
            "lp_split_pct": "85",
            "gp_split_pct": "15",
            "description": "Promote after the preferred return clears.",
        }
    )


class WaterfallTierRead(WaterfallTierBase):
    id: uuid.UUID
    scenario_id: uuid.UUID

    model_config = _example_config(
        {
            "id": _EXAMPLE_WATERFALL_TIER_ID,
            "scenario_id": _EXAMPLE_MODEL_ID,
            "capital_module_id": _EXAMPLE_CAPITAL_MODULE_ID,
            "priority": 1,
            "tier_type": "return_of_equity",
            "irr_hurdle_pct": "8.0",
            "lp_split_pct": "90",
            "gp_split_pct": "10",
            "description": "Return sponsor equity first",
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# WaterfallResult CRUD schemas
# ---------------------------------------------------------------------------

class WaterfallResultBase(BaseModel):
    period: int
    cash_distributed: Decimal = Decimal("0")
    cumulative_distributed: Decimal = Decimal("0")
    party_irr_pct: Decimal | None = None


class WaterfallResultCreate(WaterfallResultBase):
    scenario_id: uuid.UUID
    tier_id: uuid.UUID
    capital_module_id: uuid.UUID


class WaterfallResultRead(WaterfallResultBase):
    id: uuid.UUID
    scenario_id: uuid.UUID
    tier_id: uuid.UUID
    capital_module_id: uuid.UUID

    model_config = {"from_attributes": True}


class InvestorDistributionPeriodRead(BaseModel):
    period: int
    cash_distributed: Decimal = Decimal("0")
    cumulative_distributed: Decimal = Decimal("0")


class InvestorDistributionSummaryRead(BaseModel):
    capital_module_id: uuid.UUID
    investor_name: str
    funder_type: str
    stack_position: int
    committed_capital: Decimal | None = None
    total_cash_distributed: Decimal = Decimal("0")
    ending_cumulative_distributed: Decimal = Decimal("0")
    latest_party_irr_pct: Decimal | None = None
    equity_multiple: Decimal | None = None
    cash_on_cash_year_1_pct: Decimal | None = None
    share_of_total_distributions_pct: Decimal | None = None
    timeline: list[InvestorDistributionPeriodRead] = Field(default_factory=list)


class WaterfallDistributionReportRead(BaseModel):
    scenario_id: uuid.UUID
    investor_count: int = 0
    total_cash_distributed: Decimal = Decimal("0")
    investors: list[InvestorDistributionSummaryRead] = Field(default_factory=list)

    model_config = _example_config(
        {
            "scenario_id": _EXAMPLE_MODEL_ID,
            "investor_count": 1,
            "total_cash_distributed": "27000",
            "investors": [
                {
                    "capital_module_id": _EXAMPLE_CAPITAL_MODULE_ID,
                    "investor_name": "LP Equity",
                    "funder_type": "common_equity",
                    "stack_position": 1,
                    "committed_capital": "40000",
                    "total_cash_distributed": "27000",
                    "ending_cumulative_distributed": "27000",
                    "latest_party_irr_pct": "14.2",
                    "equity_multiple": "0.675",
                    "cash_on_cash_year_1_pct": "50.0",
                    "share_of_total_distributions_pct": "100.0",
                    "timeline": [
                        {
                            "period": 1,
                            "cash_distributed": "5000",
                            "cumulative_distributed": "5000",
                        }
                    ],
                }
            ],
        }
    )
