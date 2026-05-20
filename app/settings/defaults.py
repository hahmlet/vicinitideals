"""System baseline constants and Org-Set field registry.

SYSTEM_BASELINE maps every known field_key to its hardcoded fallback value
(as a string). Values are cast by callers at point of use.

ORG_SET_FIELDS is the set of field_keys that are Type 1 (Org-Set): the org
value always wins; users cannot override in the model form. Inputs for these
keys are rendered with the ``readonly`` attribute and a lock indicator in
model_builder.html.
"""

from __future__ import annotations

SYSTEM_BASELINE: dict[str, str] = {
    # ── Underwriting Policy (Org-Set / Type 1) ───────────────────────────────
    "operation_reserve_months": "6",
    "debt_sizing_mode": "gap_fill",
    "capex_reserve_per_unit_annual": "250.00",
    "risk_free_rate_pct": "4.25",
    # ── Debt & Financing (Org-Default / Type 2) ──────────────────────────────
    "dscr_min": "1.25",
    "ltv_pct": "70.0",
    "amort_term_years": "30",
    "hold_term_years": "7",
    "carry_type_construction": "io_only",
    "carry_type_permanent": "pi",
    "auto_size": "true",
    "loan_closing_origination_pct": "1.0",
    "loan_closing_legal_flat": "7500.00",
    "loan_closing_title_pct": "0.25",
    # ── Income & Revenue (Org-Default) ───────────────────────────────────────
    "income_mode": "revenue_opex",
    "stabilized_occupancy_pct": "95.0",
    "escalation_rate_pct_annual_income": "3.0",
    "noi_escalation_rate_pct": "3.0",
    "bad_debt_pct": "1.0",
    "lease_up_curve": "linear",
    # ── Operating Expenses (Org-Default) ─────────────────────────────────────
    "escalation_rate_pct_annual_opex": "3.0",
    "asset_mgmt_fee_pct": "0.5",
    "management_fee_pct": "5.0",
    "lease_up_floor_pct": "50.0",
    # ── Construction & Timeline (Org-Default) ────────────────────────────────
    "construction_floor_pct": "40.0",
    "use_line_timing": "first_day",
    # ── Exit & Disposition (Org-Default) ─────────────────────────────────────
    # TODO(org-defaults): selling_costs_pct already exists on OperationalInputs
    # with default=0. Wire resolve_all_defaults() into the OperationalInputs
    # creation block in ui.py so new deals pre-populate from org default (2.0%).
    # See docs/feature-plans/org-user-defaults.md Phase 1 item 6.
    "selling_costs_pct": "2.0",
    # ── Waterfall & Equity (Org-Default) ─────────────────────────────────────
    "lp_split_pct": "80.0",
    "gp_split_pct": "20.0",
    "irr_hurdle_pct_tier1": "8.0",
    "pref_return_rate_pct": "6.0",
    # ── Developer Fee (Org-Default, per deal_type) ───────────────────────────
    # Auto-seeded on every new deal. Engine recomputes $ each pass from
    # dev_fee_pct * basis. User overrides % in the Use drawer; $ is read-only.
    # Set dev_fee_pct_<type> to 0 to effectively disable for that deal type.
    "dev_fee_enabled": "true",
    "dev_fee_pct_acquisition": "5.0",
    "dev_fee_pct_value_add": "12.0",
    "dev_fee_pct_conversion": "12.0",
    "dev_fee_pct_new_construction": "12.0",
    "dev_fee_basis_acquisition": "purchase_price",
    "dev_fee_basis_value_add": "tpc_excl_self",
    "dev_fee_basis_conversion": "tpc_excl_self",
    "dev_fee_basis_new_construction": "tpc_excl_self",
    "dev_fee_timing_acquisition": "first_day",
    "dev_fee_timing_value_add": "spread",
    "dev_fee_timing_conversion": "spread",
    "dev_fee_timing_new_construction": "spread",
    "dev_fee_phase_acquisition": "acquisition",
    "dev_fee_phase_value_add": "construction",
    "dev_fee_phase_conversion": "construction",
    "dev_fee_phase_new_construction": "construction",
    # ── User-Default only (Type 3) ────────────────────────────────────────────
    "lease_up_curve_steepness": "5",
}

# Fields whose effective value always comes from org or system baseline.
# Users cannot override in-model. Model forms render these readonly.
ORG_SET_FIELDS: frozenset[str] = frozenset(
    {
        "operation_reserve_months",
        "debt_sizing_mode",
        "capex_reserve_per_unit_annual",
        "risk_free_rate_pct",
    }
)
