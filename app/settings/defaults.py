"""System baseline constants and Org-Set field registry.

DEFAULT_REGISTRY is the source of truth: every default-eligible field maps to
its system baseline value, target table/column, cast function, and policy type.

SYSTEM_BASELINE (dict[str, str]) and ORG_SET_FIELDS (frozenset[str]) are
derived views kept for backward compatibility with existing call sites in
resolver.py, settings UI, and the engine. New code should consume
DEFAULT_REGISTRY directly via app.services.scenario_factory.

Policy types
------------
1 = Org-Set     — org value always wins; user cannot override
2 = Org-Default — user → org → system fallback chain
3 = User-Default — user-only; no org policy ever
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable


def _bool(s: str) -> bool:
    return str(s).strip().lower() in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class DefaultSpec:
    """One row in DEFAULT_REGISTRY.

    Fields
    ------
    value : str
        System baseline as a string. Cast at apply-time via ``cast``.
    target : str
        Where the value lands when applied to a new Scenario/OperationalInputs.
        Valid values:
          - "scenario"                   → attribute on Scenario row
          - "operational_inputs"         → attribute on OperationalInputs row
          - "operational_inputs.debt_terms.permanent_debt"
                                         → JSONB sub-path on OperationalInputs.debt_terms
          - "no_destination"             → default exists but no scalar column to
                                           write into (lands on child rows like
                                           WaterfallTier, IncomeStream, UseLine
                                           that get created separately)
    column : str | None
        Attribute name on the target row or key inside the JSONB sub-path.
        None when ``target == "no_destination"``.
    cast : Callable[[str], Any]
        Function that converts the stored string value to its typed Python
        value. Use ``int`` / ``float`` / ``str`` / ``Decimal`` / ``_bool``.
    type : int
        Policy type (1, 2, or 3 — see module docstring).
    """

    value: str
    target: str
    column: str | None
    cast: Callable[[str], Any]
    type: int


# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT_REGISTRY — the single source of truth for every default-eligible field
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_REGISTRY: dict[str, DefaultSpec] = {
    # ── Underwriting Policy (Type 1 — Org-Set) ───────────────────────────────
    "operation_reserve_months": DefaultSpec(
        value="6",
        target="operational_inputs",
        column="operation_reserve_months",
        cast=int,
        type=1,
    ),
    "debt_sizing_mode": DefaultSpec(
        value="gap_fill",
        target="operational_inputs",
        column="debt_sizing_mode",
        cast=str,
        type=1,
    ),
    "capex_reserve_per_unit_annual": DefaultSpec(
        value="250.00",
        target="operational_inputs",
        column="capex_reserve_per_unit_annual",
        cast=Decimal,
        type=1,
    ),
    "risk_free_rate_pct": DefaultSpec(
        value="4.25",
        target="scenario",
        column="risk_free_rate_pct",
        cast=Decimal,
        type=1,
    ),
    # ── Debt & Financing (Type 2 — Org-Default) ──────────────────────────────
    # JSONB sub-paths on operational_inputs.debt_terms.permanent_debt
    "dscr_min": DefaultSpec(
        value="1.25",
        target="operational_inputs.debt_terms.permanent_debt",
        column="dscr_min",
        cast=float,
        type=2,
    ),
    "ltv_pct": DefaultSpec(
        value="70.0",
        target="operational_inputs.debt_terms.permanent_debt",
        column="ltv_pct",
        cast=float,
        type=2,
    ),
    "amort_term_years": DefaultSpec(
        value="30",
        target="operational_inputs.debt_terms.permanent_debt",
        column="amort_years",  # JSONB key is amort_years (not amort_term_years)
        cast=int,
        type=2,
    ),
    "hold_term_years": DefaultSpec(
        value="7",
        target="operational_inputs.debt_terms.permanent_debt",
        column="hold_term_years",
        cast=int,
        type=2,
    ),
    # Per-loan carry types and auto-sizing flag land on CapitalModule rows that
    # get created post-factory; no scalar column on Scenario/OperationalInputs.
    "carry_type_construction": DefaultSpec(
        value="io_only", target="no_destination", column=None, cast=str, type=2
    ),
    "carry_type_permanent": DefaultSpec(
        value="pi", target="no_destination", column=None, cast=str, type=2
    ),
    "auto_size": DefaultSpec(
        value="true", target="no_destination", column=None, cast=_bool, type=2
    ),
    # Loan closing-cost components land inside CapitalModule.source dict;
    # no scalar column.
    "loan_closing_origination_pct": DefaultSpec(
        value="1.0", target="no_destination", column=None, cast=float, type=2
    ),
    "loan_closing_legal_flat": DefaultSpec(
        value="7500.00", target="no_destination", column=None, cast=Decimal, type=2
    ),
    "loan_closing_title_pct": DefaultSpec(
        value="0.25", target="no_destination", column=None, cast=float, type=2
    ),
    # ── Income & Revenue (Type 2 — Org-Default) ──────────────────────────────
    "income_mode": DefaultSpec(
        value="revenue_opex",
        target="scenario",
        column="income_mode",
        cast=str,
        type=2,
    ),
    # IncomeStream-level fields — no Project/Scenario scalar; applied when
    # IncomeStream rows are seeded.
    "stabilized_occupancy_pct": DefaultSpec(
        value="95.0", target="no_destination", column=None, cast=float, type=2
    ),
    "escalation_rate_pct_annual_income": DefaultSpec(
        value="3.0", target="no_destination", column=None, cast=float, type=2
    ),
    "noi_escalation_rate_pct": DefaultSpec(
        value="3.0",
        target="operational_inputs",
        column="noi_escalation_rate_pct",
        cast=Decimal,
        type=2,
    ),
    "bad_debt_pct": DefaultSpec(
        value="1.0", target="no_destination", column=None, cast=float, type=2
    ),
    "lease_up_curve": DefaultSpec(
        value="linear",
        target="operational_inputs",
        column="lease_up_curve",
        cast=str,
        type=2,
    ),
    # ── Operating Expenses (Type 2 — Org-Default) ────────────────────────────
    "escalation_rate_pct_annual_opex": DefaultSpec(
        value="3.0", target="no_destination", column=None, cast=float, type=2
    ),
    "asset_mgmt_fee_pct": DefaultSpec(
        value="0.5",
        target="operational_inputs",
        column="asset_mgmt_fee_pct",
        cast=Decimal,
        type=2,
    ),
    "management_fee_pct": DefaultSpec(
        value="5.0",
        target="operational_inputs",
        column="mgmt_fee_pct",  # column on OperationalInputs is mgmt_fee_pct
        cast=Decimal,
        type=2,
    ),
    "lease_up_floor_pct": DefaultSpec(
        value="50.0", target="no_destination", column=None, cast=float, type=2
    ),
    # ── Construction & Timeline (Type 2 — Org-Default) ───────────────────────
    "construction_floor_pct": DefaultSpec(
        value="40.0",
        target="operational_inputs",
        column="construction_floor_pct",
        cast=Decimal,
        type=2,
    ),
    "use_line_timing": DefaultSpec(
        value="first_day", target="no_destination", column=None, cast=str, type=2
    ),
    # ── Exit & Disposition (Type 2 — Org-Default) ────────────────────────────
    "selling_costs_pct": DefaultSpec(
        value="2.0",
        target="operational_inputs",
        column="selling_costs_pct",
        cast=Decimal,
        type=2,
    ),
    # ── Waterfall & Equity (Type 2 — Org-Default) ────────────────────────────
    # WaterfallTier child rows — no scenario-level scalar columns.
    "lp_split_pct": DefaultSpec(
        value="80.0", target="no_destination", column=None, cast=float, type=2
    ),
    "gp_split_pct": DefaultSpec(
        value="20.0", target="no_destination", column=None, cast=float, type=2
    ),
    "irr_hurdle_pct_tier1": DefaultSpec(
        value="8.0", target="no_destination", column=None, cast=float, type=2
    ),
    "pref_return_rate_pct": DefaultSpec(
        value="6.0", target="no_destination", column=None, cast=float, type=2
    ),
    # ── Developer Fee (Type 2 — Org-Default, per deal_type) ──────────────────
    # Auto-seeded into a UseLine row on every new deal by the dev fee engine;
    # no scalar column.
    "dev_fee_enabled": DefaultSpec(
        value="true", target="no_destination", column=None, cast=_bool, type=2
    ),
    "dev_fee_pct_acquisition": DefaultSpec(
        value="5.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_pct_value_add": DefaultSpec(
        value="12.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_pct_conversion": DefaultSpec(
        value="12.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_pct_new_construction": DefaultSpec(
        value="12.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_basis_acquisition": DefaultSpec(
        value="purchase_price", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_basis_value_add": DefaultSpec(
        value="tpc_excl_self", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_basis_conversion": DefaultSpec(
        value="tpc_excl_self", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_basis_new_construction": DefaultSpec(
        value="tpc_excl_self", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_timing_acquisition": DefaultSpec(
        value="first_day", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_timing_value_add": DefaultSpec(
        value="spread", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_timing_conversion": DefaultSpec(
        value="spread", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_timing_new_construction": DefaultSpec(
        value="spread", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_phase_acquisition": DefaultSpec(
        value="acquisition", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_phase_value_add": DefaultSpec(
        value="construction", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_phase_conversion": DefaultSpec(
        value="construction", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_phase_new_construction": DefaultSpec(
        value="construction", target="no_destination", column=None, cast=str, type=2
    ),
    # Dev Fee multi-source (migration 0103): acquisition treatment + holdback +
    # milestone weights per deal type. Treatments: excluded / split_rate /
    # separate_fee.
    "dev_fee_acquisition_treatment_acquisition": DefaultSpec(
        value="separate_fee", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_acquisition_treatment_value_add": DefaultSpec(
        value="split_rate", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_acquisition_treatment_conversion": DefaultSpec(
        value="excluded", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_acquisition_treatment_new_construction": DefaultSpec(
        value="excluded", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_acquisition_pct_acquisition": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_acquisition_pct_value_add": DefaultSpec(
        value="1.5", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_acquisition_pct_conversion": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_acquisition_pct_new_construction": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "acquisition_fee_pct_acquisition": DefaultSpec(
        value="2.0", target="no_destination", column=None, cast=float, type=2
    ),
    "acquisition_fee_pct_value_add": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "acquisition_fee_pct_conversion": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "acquisition_fee_pct_new_construction": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_final_holdback_pct_acquisition": DefaultSpec(
        value="0.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_final_holdback_pct_value_add": DefaultSpec(
        value="10.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_final_holdback_pct_conversion": DefaultSpec(
        value="10.0", target="no_destination", column=None, cast=float, type=2
    ),
    "dev_fee_final_holdback_pct_new_construction": DefaultSpec(
        value="10.0", target="no_destination", column=None, cast=float, type=2
    ),
    # Milestone weights stored as a JSON-encoded list of
    # {milestone_type: weight}. Empty default = no schedule (release at
    # close); orgs populate via the UseLine drawer.
    "dev_fee_milestone_weights_acquisition": DefaultSpec(
        value="[]", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_milestone_weights_value_add": DefaultSpec(
        value="[]", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_milestone_weights_conversion": DefaultSpec(
        value="[]", target="no_destination", column=None, cast=str, type=2
    ),
    "dev_fee_milestone_weights_new_construction": DefaultSpec(
        value="[]", target="no_destination", column=None, cast=str, type=2
    ),
    # ── User-Default only (Type 3) ───────────────────────────────────────────
    "lease_up_curve_steepness": DefaultSpec(
        value="5",
        target="operational_inputs",
        column="lease_up_curve_steepness",
        cast=Decimal,
        type=3,
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compatible derived views — keep existing call sites working.
# resolver.py, settings UI, and engine code import these by name.
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_BASELINE: dict[str, str] = {k: v.value for k, v in DEFAULT_REGISTRY.items()}

# Fields whose effective value always comes from org or system baseline.
# Users cannot override in-model. Model forms render these readonly.
ORG_SET_FIELDS: frozenset[str] = frozenset(
    k for k, v in DEFAULT_REGISTRY.items() if v.type == 1
)
