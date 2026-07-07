"""Canonical cross-surface vocabulary — single source of truth.

Every surface that enumerates a model vocabulary (Pydantic Literals, template
dropdowns, Excel data-validation lists, settings guards, error strings) must
derive from — or be asserted equal to — the constants here. The contract test
``tests/contract/test_vocab_sync.py`` enforces this; if you add a value to a
model enum or a Literal below, that test tells you every surface to update.

Two kinds of constants live here:

* **Enum-derived tuples** (``VEHICLE_TYPES`` …) — computed from the ORM enums
  so they can never drift from the database vocabulary.
* **Literal aliases** (``CarryTypeLiteral`` …) — for JSONB-column
  vocabularies that have no ORM enum. ``typing.Literal`` cannot be built
  dynamically, so these are spelled out and the contract test asserts their
  args match the companion tuple.
"""

from __future__ import annotations

from typing import Literal

from app.models.capital import EquityRole, VehicleType, WaterfallTierType
from app.models.deal import (
    IncomeStreamType,
    ProjectType,
    UseLinePhase,
    UseLineTiming,
)
from app.models.opportunity import OpportunitySource

# ---------------------------------------------------------------------------
# Enum-derived tuples
# ---------------------------------------------------------------------------

VEHICLE_TYPES: tuple[str, ...] = tuple(v.value for v in VehicleType)
EQUITY_ROLES: tuple[str, ...] = tuple(r.value for r in EquityRole)
WATERFALL_TIER_TYPES: tuple[str, ...] = tuple(t.value for t in WaterfallTierType)
USE_LINE_PHASES: tuple[str, ...] = tuple(p.value for p in UseLinePhase)
USE_LINE_TIMINGS: tuple[str, ...] = tuple(t.value for t in UseLineTiming)
INCOME_STREAM_TYPES: tuple[str, ...] = tuple(s.value for s in IncomeStreamType)
PROJECT_TYPES: tuple[str, ...] = tuple(p.value for p in ProjectType)
OPPORTUNITY_SOURCES: tuple[str, ...] = tuple(s.value for s in OpportunitySource)

# ---------------------------------------------------------------------------
# JSONB vocabularies (no ORM enum) — tuple + Literal alias pairs
# ---------------------------------------------------------------------------

# Carry types accepted in CapitalCarrySchema.carry_type (flat shape).
CARRY_TYPES: tuple[str, ...] = (
    "io_only",
    "interest_reserve",
    "capitalized_interest",
    "accruing",
    "pi",
    "none",
)
CarryTypeLiteral = Literal[
    "io_only",
    "interest_reserve",
    "capitalized_interest",
    "accruing",
    "pi",
    "none",
]

# Phase-level carry additionally allows `converts_to_permanent`, a
# construction-phase sentinel meaning "this loan's balance rolls into the
# permanent loan when operation starts". It is valid ONLY inside
# ``carry.phases[]`` / ``carry.schedule[]`` entries, never as the flat
# ``carry_type``.
PHASE_CARRY_TYPES: tuple[str, ...] = CARRY_TYPES + ("converts_to_permanent",)

# Interest day-count conventions (CapitalCarrySchema.day_count).
DAY_COUNTS: tuple[str, ...] = ("30_360", "actual_365", "actual_360")
DayCountLiteral = Literal["30_360", "actual_365", "actual_360"]

VehicleTypeLiteral = Literal[
    "equity",
    "debt",
    "forgivable_loan",
    "grant",
    "float_earnings",
    "deferred_developer_fee",
]
EquityRoleLiteral = Literal["gp", "lp"]

# ---------------------------------------------------------------------------
# active_phase_start / active_phase_end vocabulary
# ---------------------------------------------------------------------------
# CapitalModule.active_phase_start is a free String(60) column with no ORM
# enum. This is the authoritative key set; the per-consumer maps
# (`_CM_PHASE_TO_MS` in ui_model_builder, `_APS_TO_MS` in
# model_builder_forms/capital_module, `_APS_TO_RANK` in cashflow_compile)
# intentionally cover different subsets with different targets, but every
# key they use must be listed here.
ACTIVE_PHASE_KEYS: tuple[str, ...] = (
    "acquisition",
    "close",
    "pre_development",
    "pre_construction",
    "construction",
    "lease_up",
    "operation_lease_up",
    "stabilized",
    "operation_stabilized",
    "exit",
    "divestment",
    "perpetuity",  # legacy sentinel: runs through divestment
)
