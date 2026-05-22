# Defaults Coverage Audit

Generated: 2026-05-21. Reflects state after the `scenario_factory.create_scenario()`
unified deal-creation factory ships (wizard-refactor branch).

Every entry in `app/settings/defaults.py::DEFAULT_REGISTRY` is enumerated below
with its target (where the resolved value lands on a freshly created Scenario or
OperationalInputs row) and whether the value actually reaches the engine.

Legend
- ✅ Reaches — value lands on a scalar column or JSONB sub-path that the engine reads.
- ❌ No destination — registry has a value, but there is no scalar column / no row
  on which to write it. These are "future work" items: either the engine needs to
  read defaults directly (no row required), or the factory needs to seed a child
  row (`WaterfallTier`, `IncomeStream`, etc.) on create.

## Type 1 — Org-Set (org value always wins; user cannot override)

| field_key | Baseline | Target | Reaches Deal? | Notes |
|---|---|---|---|---|
| `operation_reserve_months` | 6 | `operational_inputs.operation_reserve_months` | ✅ | Engine reads it |
| `debt_sizing_mode` | gap_fill | `operational_inputs.debt_sizing_mode` | ✅ | Engine reads it |
| `capex_reserve_per_unit_annual` | 250.00 | `operational_inputs.capex_reserve_per_unit_annual` | ✅ | NEW — factory writes (was NULL pre-refactor) |
| `risk_free_rate_pct` | 4.25 | `scenario.risk_free_rate_pct` | ✅ | NEW — factory writes (was NULL pre-refactor) |

## Type 2 — Org-Default (user → org → system fallback)

### Scenario / OperationalInputs scalars

| field_key | Baseline | Target | Reaches Deal? | Notes |
|---|---|---|---|---|
| `income_mode` | revenue_opex | `scenario.income_mode` | ✅ | Engine reads it |
| `noi_escalation_rate_pct` | 3.0 | `operational_inputs.noi_escalation_rate_pct` | ✅ | Engine reads it |
| `lease_up_curve` | linear | `operational_inputs.lease_up_curve` | ✅ | Engine reads it |
| `asset_mgmt_fee_pct` | 0.5 | `operational_inputs.asset_mgmt_fee_pct` | ✅ | Engine reads it |
| `management_fee_pct` | 5.0 | `operational_inputs.mgmt_fee_pct` | ✅ | Column name mismatch handled by registry (`column="mgmt_fee_pct"`) |
| `construction_floor_pct` | 40.0 | `operational_inputs.construction_floor_pct` | ✅ | Engine reads it |
| `selling_costs_pct` | 2.0 | `operational_inputs.selling_costs_pct` | ✅ | Engine reads it |

### Permanent debt JSONB (operational_inputs.debt_terms.permanent_debt)

| field_key | Baseline | Target | Reaches Deal? | Notes |
|---|---|---|---|---|
| `dscr_min` | 1.25 | `…permanent_debt.dscr_min` | ✅ | Engine reads it |
| `ltv_pct` | 70.0 | `…permanent_debt.ltv_pct` | ✅ | Engine reads it |
| `amort_term_years` | 30 | `…permanent_debt.amort_years` | ✅ | Key in JSONB is `amort_years` (registry handles the rename) |
| `hold_term_years` | 7 | `…permanent_debt.hold_term_years` | ✅ | Engine reads it |

### No destination — fields with a baseline but no scalar landing spot

These are NOT bugs — they live in tables/rows the factory does not currently
create. Each is a candidate for future work.

| field_key | Baseline | Future-work note |
|---|---|---|
| `carry_type_construction` | io_only | Belongs on a per-loan `CapitalModule.carry.type`. Factory does not seed loan modules — those are picked in Step 2 of the Setup Wizard. |
| `carry_type_permanent` | pi | Same — per-loan `CapitalModule.carry.type` on the permanent loan. |
| `auto_size` | true | Per-loan `CapitalModule.source.auto_size`. Same future-work as carry. |
| `loan_closing_origination_pct` | 1.0 | Lands inside `CapitalModule.source.closing_costs[*].pct` when a loan module is created. |
| `loan_closing_legal_flat` | 7500.00 | Same — `CapitalModule.source.closing_costs[*].amount` for the legal line. |
| `loan_closing_title_pct` | 0.25 | Same — `CapitalModule.source.closing_costs[*].pct` for the title line. |
| `stabilized_occupancy_pct` | 95.0 | Per-IncomeStream value. No IncomeStreams seeded at create — pro forma upload or manual entry populates them. |
| `escalation_rate_pct_annual_income` | 3.0 | Same — per-IncomeStream. |
| `bad_debt_pct` | 1.0 | Same — per-IncomeStream. |
| `escalation_rate_pct_annual_opex` | 3.0 | Per-ExpenseLine value. No ExpenseLines seeded at create. |
| `lease_up_floor_pct` | 50.0 | Per-IncomeStream. |
| `use_line_timing` | first_day | Per-UseLine value. Acquisition UseLine seeded by the create handler already uses `"first_day"` literally; default isn't read from registry yet. |
| `lp_split_pct` | 80.0 | Belongs on a default `WaterfallTier` row. No tiers seeded at create — the deal's waterfall is built by the user (or future seed helper). |
| `gp_split_pct` | 20.0 | Same — `WaterfallTier`. |
| `irr_hurdle_pct_tier1` | 8.0 | Same — first `WaterfallTier.hurdle_rate`. Also wired explicitly to `scenario.discount_rate_pct` in the wizard fallback. |
| `pref_return_rate_pct` | 6.0 | Same — preferred return tier. |
| `dev_fee_enabled` | true | Auto-seeded as a `UseLine` row by `/ui/deals/create` (resolves via `resolve_dev_fee_config`). Not directly on Scenario/OpInputs. |
| `dev_fee_pct_acquisition` | 5.0 | Per-deal-type: read by `resolve_dev_fee_config` and lands on the seeded Developer Fee `UseLine.dev_fee_pct`. ✅ effectively reaches deal. |
| `dev_fee_pct_value_add` | 12.0 | Same. ✅ effectively reaches deal. |
| `dev_fee_pct_conversion` | 12.0 | Same. ✅ effectively reaches deal. |
| `dev_fee_pct_new_construction` | 12.0 | Same. ✅ effectively reaches deal. |
| `dev_fee_basis_acquisition` | purchase_price | Same — `UseLine.dev_fee_basis`. ✅ |
| `dev_fee_basis_value_add` | tpc_excl_self | Same. ✅ |
| `dev_fee_basis_conversion` | tpc_excl_self | Same. ✅ |
| `dev_fee_basis_new_construction` | tpc_excl_self | Same. ✅ |
| `dev_fee_timing_acquisition` | first_day | Same — `UseLine.timing_type`. ✅ |
| `dev_fee_timing_value_add` | spread | Same. ✅ |
| `dev_fee_timing_conversion` | spread | Same. ✅ |
| `dev_fee_timing_new_construction` | spread | Same. ✅ |
| `dev_fee_phase_acquisition` | acquisition | Same — `UseLine.phase`. ✅ |
| `dev_fee_phase_value_add` | construction | Same. ✅ |
| `dev_fee_phase_conversion` | construction | Same. ✅ |
| `dev_fee_phase_new_construction` | construction | Same. ✅ |

## Type 3 — User-Default (user-only; no org policy)

| field_key | Baseline | Target | Reaches Deal? | Notes |
|---|---|---|---|---|
| `lease_up_curve_steepness` | 5 | `operational_inputs.lease_up_curve_steepness` | ✅ | Engine reads it |

## Summary

- **Direct scalar / JSONB lands**: 16 fields reach via the factory's
  `_apply_scenario_defaults` / `_apply_operational_inputs_defaults` passes.
- **Dev fee block (13 fields)**: not a scalar landing, but reaches the deal as a
  seeded `UseLine` row via the existing `resolve_dev_fee_config` path.
- **No destination yet (16 fields)**: carry-type, loan closing costs, income-stream
  fields, opex-line fields, waterfall tiers, per-use-line timing. None block the
  wizard refactor — these were always populated downstream (loan terms wizard,
  pro forma upload, waterfall builder) or hard-coded by route handlers.

## Future Work Backlog

1. **Auto-seed default `WaterfallTier` rows on Scenario create.** Today the deal
   ships with no tiers and the user builds them in the waterfall panel.
   Pre-seeding tier 1 with `lp_split_pct` / `gp_split_pct` / `irr_hurdle_pct_tier1`
   from registry would let the engine compute a defensible distribution from
   day one.
2. **Wire per-loan `CapitalModule` carry/auto_size/closing-cost defaults** to
   pull from the registry when a loan is added via Step 2 (vehicle vs. blank).
   Today they come from `_DEFAULT_LOAN_COSTS` in `cashflow.py`; consolidating to
   the registry would eliminate the duplicate table.
3. **IncomeStream / ExpenseLine seeding** — when the user picks `noi` income mode
   or skips the pro forma upload, the factory could pre-seed a single
   IncomeStream row with `stabilized_occupancy_pct`, `bad_debt_pct`,
   `escalation_rate_pct_annual_income`, and similarly an ExpenseLine row with
   `escalation_rate_pct_annual_opex`. Today these stay empty until manual entry.
4. **Rename mismatch cleanup**: `management_fee_pct` (registry) →
   `mgmt_fee_pct` (column) and `amort_term_years` (registry) → `amort_years`
   (JSONB key). Either rename the registry keys for consistency or document the
   mapping permanently — current `column=` override on `DefaultSpec` handles it.
