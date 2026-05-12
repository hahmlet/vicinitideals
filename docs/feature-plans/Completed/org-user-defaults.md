# Feature Plan: Org & User Default Settings System

## Overview

This plan defines a structured defaults system for every user-facing input field in the Viciniti Deals financial model. It establishes which fields should be locked by organization policy, which carry editable org-level starting points, which reflect individual analyst preferences, and which must always be entered fresh per deal.

The design is MF-primary (multifamily is the sole target property type at launch). Global defaults will be used; per-property-type defaults can be layered on in a future version without schema migration.

Market-driven values (cap rates, rents, comp-based metrics) are intentionally excluded from this defaults system — they are owned by the KNN algorithm and surfaced to the model as suggestions, not defaults.

---

## The Five Default Types

| # | Type | Label | Who Sets It | Can User Edit In-Model? | Notes |
|---|------|-------|-------------|--------------------------|-------|
| 1 | **Org-Set** | Locked | Org Admin | No | Policy or methodology enforcement |
| 2 | **Org-Default** | Editable | Org Admin | Yes | Org provides starting point; user overrides in-model |
| 3 | **User-Default** | Personal | User (Settings menu) | Yes | Analyst's own preferences; overrides Org-Default |
| 4 | **No Default** | Blank | N/A | N/A — must be entered | Deal-specific; no reasonable guess |
| 5 | **Silent Default** | Hidden | Codebase | No | Only for existing engine internals |

**Resolution order at model open:** User-Default → Org-Default → System Baseline (hardcoded starting value before any settings are configured).

Org-Set fields bypass this chain — the org-stored value is used unconditionally. If the org has not yet configured an Org-Set field, the System Baseline is used and the model should surface a visual indicator that org setup is incomplete.

---

## Constraint-Aware Storage Design

### Why This Matters

Currently, a default is a single value (e.g., `dscr_min = 1.25`). A future enhancement will allow orgs to configure a **range** (DSCR: 1.15–1.25) or a **list** (CapEx Reserve: $200, $250, $300) that constrains what users can enter. Without planning for this now, adding it later requires a schema migration + full-stack rework of every affected form.

### Design Approach

Store every default (both org and user) as a structured row, not a bare column. The constraint fields are nullable — they have no effect until populated.

**`org_settings` table schema:**
```
id                  uuid        PK
org_id              uuid        FK → organizations
field_key           text        NOT NULL  (e.g. "dscr_min", "capex_reserve_per_unit")
value               text        NOT NULL  (stored as text; cast at read time)
constraint_type     text        NULL      — "range" | "list" | null
constraint_min      numeric     NULL      — for range type
constraint_max      numeric     NULL      — for range type
constraint_options  jsonb       NULL      — for list type: [200, 250, 300]
updated_at          timestamptz
updated_by          uuid        FK → users
```

**`user_settings` table schema:**
```
id                  uuid        PK
user_id             uuid        FK → users
org_id              uuid        FK → organizations
field_key           text        NOT NULL
value               text        NOT NULL
updated_at          timestamptz
```

### Resolution Logic (pseudo-code for engine/API layer)

```python
def resolve_default(field_key, user_id, org_id):
    # 1. If Org-Set type: always return org value (ignore user setting)
    if field_key in ORG_SET_FIELDS:
        return org_settings.get(org_id, field_key) or SYSTEM_BASELINE[field_key]

    # 2. User-Default: check user settings first
    user_val = user_settings.get(user_id, field_key)
    if user_val:
        return user_val

    # 3. Org-Default: fall back to org setting
    org_val = org_settings.get(org_id, field_key)
    if org_val:
        return org_val

    # 4. Fall back to system baseline
    return SYSTEM_BASELINE.get(field_key)  # None if No Default type
```

### Constraint Enforcement (future — not implemented now)

When `constraint_type` is populated on an `org_settings` row:
- **range**: reject in-model edits outside `[constraint_min, constraint_max]`
- **list**: restrict in-model field to a picker showing `constraint_options` only

The UI and API validation layer reads these fields at runtime. Until populated, behavior is identical to today.

---

## Field Inventory by Category

### Legend
- **Type**: 1=Org-Set, 2=Org-Default, 3=User-Default, 4=No Default, 5=Silent Default
- **System Baseline**: The value pre-loaded for orgs/users who haven't configured settings yet
- **Future Constraint**: None / Range / List
- **UI Group**: The collapsible section this field belongs to in the Settings UI (see Settings UI Layout section). Type 4 fields do not appear in the Settings UI.

---

### Category 1: Uses / Costs

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Use line amount | `UseLine.amount` | 4 | — | None | — | — | Dollar amount; deal-specific |
| Use line label | `UseLine.label` | 4 | — | List | Standard MF categories | — | Template pre-population is a separate feature |
| Use line phase | `UseLine.phase` | 4 | — | None | — | — | Deal-specific sequencing |
| Use line timing | `UseLine.timing` | 2 | `first_day` | List | `first_day`, `spread` | Construction & Timeline | `spread` is typical for construction soft costs |
| Operating reserve months | `OperationalInputs.operation_reserve_months` | 1 | 6 months | Range | 3–12 months | Underwriting Policy | Policy; drives operating reserve use-line size |
| Loan closing costs (origination) | `_DEFAULT_LOAN_COSTS.origination_pct` | 2 | 1.0% of loan | Range | 0.5–2.0% | Debt & Financing | Per funder type; analyst can override per deal |
| Loan closing costs (legal) | `_DEFAULT_LOAN_COSTS.legal_flat` | 2 | $7,500 | Range | $3,000–$15,000 | Debt & Financing | Per funder type |
| Loan closing costs (title/escrow) | `_DEFAULT_LOAN_COSTS.title_pct` | 2 | 0.25% of loan | Range | 0.1–0.5% | Debt & Financing | Per funder type |

---

### Category 2: Debt / Capital Sources

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Debt sizing mode | `OperationalInputs.debt_sizing_mode` | 1 | `gap_fill` | List | `gap_fill`, `dscr_capped`, `dual_constraint` | Underwriting Policy | Methodology lock; org defines underwriting convention |
| Interest rate | `CapitalSourceSchema.interest_rate_pct` | 4 | — | Range | 2.0–12.0% | — | Market-dependent; must be entered per deal |
| Amortization term | `CapitalSourceSchema.amort_term_years` | 2 | 30 years | List | 20, 25, 30 | Debt & Financing | Standard MF permanent debt |
| Hold/loan term | `CapitalSourceSchema.hold_term_years` | 3 | 7 years | Range | 3–15 years | My Preferences | Analyst's typical hold period preference |
| DSCR minimum | `CapitalSourceSchema.dscr_min` | 2 | 1.25 | Range | 1.15–1.35 | Debt & Financing | Org-Default; analyst editable in-model |
| LTV cap | `CapitalSourceSchema.ltv_pct` | 2 | 70% | Range | 60–80% | Debt & Financing | Org sets lending assumption; analyst adjusts per lender |
| Carry type | `CapitalSourceSchema.carry_type` | 2 | `io_only` (construction) / `pi` (perm) | List | All 4 carry types | Debt & Financing | Org default per funder type category |
| Prepay penalty | `CapitalSourceSchema.prepay_penalty_pct` | 4 | — | Range | 0–5% | — | Deal-specific; no reasonable default |
| Refi cap rate override | `CapitalSourceSchema.refi_cap_rate_pct` | 4 | — | None | — | — | Optional override; blank = use exit cap rate |
| Auto-size flag | `CapitalModuleProject.auto_size` | 2 | `True` | None | — | Debt & Financing | Default to engine-sized; analyst can lock per project |
| Exit vehicle | `CapitalSourceSchema.exit_terms.vehicle` | 4 | — | List | `sale`, `maturity`, loan UUID | — | Deal structure decision |

---

### Category 3: Income / Revenue

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Income mode | `Scenario.income_mode` | 2 | `revenue_opex` | List | `revenue_opex`, `noi` | Income & Revenue | Org default to detailed mode; NOI mode for quick screen |
| NOI escalation rate | `OperationalInputs.noi_escalation_rate_pct` | 2 | 3.0% | Range | 1–5% | Income & Revenue | Used in NOI-direct mode only |
| Unit count | `IncomeStream.unit_count` | 4 | — | None | — | — | Physical; must be entered |
| Monthly rent per unit | `IncomeStream.amount_per_unit_monthly` | 4 | — | None | — | — | Market-driven via KNN; user confirms |
| Stabilized occupancy | `IncomeStream.stabilized_occupancy_pct` | 2 | 95% | Range | 88–98% | Income & Revenue | MF standard; analyst adjusts for submarket |
| Rent escalation rate | `IncomeStream.escalation_rate_pct_annual` | 2 | 3.0% | Range | 1–5% | Income & Revenue | Inherits from `noi_escalation_rate_pct` default |
| Bad debt % | `IncomeStream.bad_debt_pct` | 2 | 1.0% | Range | 0–3% | Income & Revenue | Standard MF underwriting convention |
| Concessions % | `IncomeStream.concessions_pct` | 4 | — | Range | 0–5% | — | Deal/market-specific; no default appropriate |
| Unit strategy | `UnitMix.unit_strategy` | 4 | — | List | `base_escalation`, `ltl_catchup`, `value_add_renovation` | — | Deal type determines this |
| Lease-up curve type | `OperationalInputs.lease_up_curve` | 2 | `linear` | List | `linear`, `s_curve` | Income & Revenue | Org preference; s-curve better for large projects |
| S-curve steepness | `OperationalInputs.lease_up_curve_steepness` | 3 | 5 | Range | 1–10 | My Preferences | Analyst preference when s-curve is used |
| Initial occupancy % | `OperationalInputs.initial_occupancy_pct` | 4 | — | Range | 0–100% | — | Depends on deal type (new construction vs. acquisition) |

---

### Category 4: Operating Expenses

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| OpEx annual amount | `OperatingExpenseLine.annual_amount` | 4 | — | None | — | — | Property-specific; must be entered |
| OpEx escalation rate | `OperatingExpenseLine.escalation_rate_pct_annual` | 2 | 3.0% | Range | 2–5% | Operating Expenses | Org consistency; same rate as income escalation recommended |
| Scale with lease-up flag | `OperatingExpenseLine.scale_with_lease_up` | 2 | `False` | None | — | Operating Expenses | Org default fixed; analyst toggles variable expenses |
| Lease-up expense floor % | `OperatingExpenseLine.lease_up_floor_pct` | 2 | 50% | Range | 0–100% | Operating Expenses | Applied when scale_with_lease_up = True |
| CapEx reserve per unit/year | `OperationalInputs.capex_reserve_per_unit_annual` | 1 | $250/unit/yr | List | $150, $200, $250, $300, $400 | Underwriting Policy | Org policy; MF standard ranges by vintage/condition |
| Asset management fee % | `OperationalInputs.asset_mgmt_fee_pct` | 2 | 0.5% | Range | 0–1.5% | Operating Expenses | % of positive NCF paid to asset manager |
| Property management fee % | *(OpEx line; see Notes)* | 2 | 5.0% of EGI | Range | 3–8% | Operating Expenses | Standard MF; entered as OpEx line — suggest as template line |

> **Note on property management fee:** There is no dedicated `management_fee_pct` ORM field — this is entered as an `OperatingExpenseLine`. A future scenario-template feature should pre-populate common MF expense lines (management fee, insurance, utilities, maintenance) with Org-Default values rather than leaving a blank list.

---

### Category 5: Timeline / Milestones

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Milestone label | `Milestone.label` | 4 | — | None | — | — | Descriptive; analyst names phases |
| Milestone phase type | `Milestone.phase_type` | 4 | — | List | All phase enum values | — | Drives which income/expense lines are active |
| Milestone duration | `Milestone.duration_days` | 4 | — | Range | 30–1,825 days | — | Deal-specific; trigger chain supersedes when wired |
| Trigger milestone link | `Milestone.trigger_milestone_id` | 4 | — | None | — | — | Multi-project chaining; deal-specific |
| Construction floor % | `OperationalInputs.construction_floor_pct` | 2 | 40% | Range | 25–60% | Construction & Timeline | % of TPC held during construction for reserve/sequencing |

---

### Category 6: Exit Assumptions

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Exit cap rate | `OperationalInputs.exit_cap_rate_pct` | 4 | — | Range | 3–10% | — | KNN-suggested; user must confirm per deal |
| Going-in cap rate | `OperationalInputs.going_in_cap_rate_pct` | 4 | — | Range | 3–10% | — | KNN-suggested; user must confirm |
| Risk-free rate (discount rate) | `OperationalInputs.risk_free_rate_pct` | 1 | 4.25% | Range | 2–7% | Underwriting Policy | Org policy; reflects org's Treasury benchmark at underwriting |
| Selling costs % | `OperationalInputs.selling_costs_pct` | 2 | 2.0% | Range | 1–4% | Exit & Disposition | Brokerage + closing costs as % of sale price; Org-Default, analyst editable in-model. Currently hardcoded in engine — must be surfaced as `OperationalInputs` field in Phase 1. |

---

### Category 7: Waterfall / Equity Structure

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| Waterfall tier type | `WaterfallTier.tier_type` | 4 | — | List | All tier type enums | — | Structure is deal-specific |
| LP split % | `WaterfallTier.lp_split_pct` | 2 | 80% | Range | 50–95% | Waterfall & Equity | Standard MF syndication starting point |
| GP split % | `WaterfallTier.gp_split_pct` | 2 | 20% | Range | 5–50% | Waterfall & Equity | Derived from LP split; should be linked |
| IRR hurdle % | `WaterfallTier.irr_hurdle_pct` | 2 | 8% (first hurdle) | Range | 5–20% | Waterfall & Equity | Org's typical promote threshold |
| Preferred return rate | `CapitalSourceSchema.pref_return_rate_pct` | 2 | 6% | Range | 4–10% | Waterfall & Equity | Org typical; varies by equity partner |
| Equity funder type | `CapitalModule.funder_type` (equity variants) | 4 | — | List | All equity enum values | — | Deal-specific capital structure |

---

### Category 8: Return Thresholds / Investment Gates

| Field | ORM Key | Type | System Baseline | Future Constraint | Constraint Params | UI Group | Notes |
|-------|---------|------|-----------------|-------------------|-------------------|----------|-------|
| DSCR minimum (gate) | `CapitalSourceSchema.dscr_min` | 2 | 1.25 | Range | 1.15–1.35 | Debt & Financing | Same field as Category 2; Org-Default, analyst editable in-model |
| LTV max (gate) | `CapitalSourceSchema.ltv_pct` | 2 | 70% | Range | 60–80% | Debt & Financing | Same field as Category 2 |
| IRR hurdle (promote gate) | `WaterfallTier.irr_hurdle_pct` | 2 | 8% | Range | 6–18% | Waterfall & Equity | Same field as Category 7 |
| Discount rate for NPV | `OperationalInputs.risk_free_rate_pct` | 1 | 4.25% | Range | 2–7% | Underwriting Policy | Same field as Category 6; Org-Set |
| Target unlevered yield-on-cost | *(not yet a stored field — see Open Items)* | 2 | 5.5% | Range | 4–8% | Underwriting Policy | Org benchmark for go/no-go screening; field needs to be added |

---

## Settings UI Layout

This section defines how the settings pages should be organized into collapsible groups. It is the authoritative reference for any agent building the Org Admin Settings page or the User Settings page.

**Rule:** Only Type 1, 2, and 3 fields appear in the Settings UI. Type 4 (No Default) fields are never shown in settings — they are always entered per-deal. Type 5 (Silent Default) fields are never shown anywhere.

---

### Org Admin Settings Page

Seven collapsible groups. Underwriting Policy should be expanded by default; all others collapsed.

#### 1. Underwriting Policy *(Org-Set — all fields in this group are locked for users)*
Fields in this group cannot be overridden by analysts. Displayed with a lock icon in both the settings page and in-model.

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Debt Sizing Method | `debt_sizing_mode` | Gap Fill |
| Operating Reserve | `operation_reserve_months` | 6 months |
| CapEx Reserve (per unit/yr) | `capex_reserve_per_unit_annual` | $250 |
| Discount Rate (Risk-Free) | `risk_free_rate_pct` | 4.25% |
| Target Yield-on-Cost | `target_yoc_pct` | 5.5% *(field not yet in ORM — see Open Items)* |

#### 2. Debt & Financing *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| DSCR Minimum | `dscr_min` | 1.25 |
| Max LTV | `ltv_pct` | 70% |
| Amortization Term | `amort_term_years` | 30 years |
| Default Carry Type (Construction) | `carry_type_construction` | Interest Only |
| Default Carry Type (Permanent) | `carry_type_permanent` | P&I |
| Auto-Size Loans | `auto_size` | Yes |
| Loan Closing — Origination | `loan_closing_origination_pct` | 1.0% |
| Loan Closing — Legal (flat) | `loan_closing_legal_flat` | $7,500 |
| Loan Closing — Title/Escrow | `loan_closing_title_pct` | 0.25% |

#### 3. Income & Revenue *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Default Income Mode | `income_mode` | Detailed (Revenue/OpEx) |
| Stabilized Occupancy | `stabilized_occupancy_pct` | 95% |
| Rent Escalation Rate | `escalation_rate_pct_annual_income` | 3.0% |
| NOI Escalation Rate | `noi_escalation_rate_pct` | 3.0% |
| Bad Debt % | `bad_debt_pct` | 1.0% |
| Lease-Up Curve | `lease_up_curve` | Linear |

#### 4. Operating Expenses *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Expense Escalation Rate | `escalation_rate_pct_annual_opex` | 3.0% |
| Asset Management Fee | `asset_mgmt_fee_pct` | 0.5% |
| Property Management Fee | `management_fee_pct` | 5.0% EGI |
| Variable Expense Lease-Up Floor | `lease_up_floor_pct` | 50% |

#### 5. Construction & Timeline *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Construction Reserve Floor | `construction_floor_pct` | 40% |
| Default Use Line Timing | `use_line_timing` | First Day of Phase |

#### 6. Exit & Disposition *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Selling Costs | `selling_costs_pct` | 2.0% |

#### 7. Waterfall & Equity *(Org-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| LP Split | `lp_split_pct` | 80% |
| GP Split | `gp_split_pct` | 20% |
| IRR Hurdle (Tier 1) | `irr_hurdle_pct_tier1` | 8% |
| Preferred Return Rate | `pref_return_rate_pct` | 6% |

---

### User Settings Page ("My Preferences")

One collapsible group. Simple page — analysts set their personal starting points. Expanded by default.

#### My Underwriting Preferences *(User-Default — analyst editable in-model)*

| Field Label | field_key | System Baseline |
|-------------|-----------|-----------------|
| Default Hold / Loan Term | `hold_term_years` | 7 years |
| S-Curve Steepness | `lease_up_curve_steepness` | 5 (medium) |

> Additional User-Default fields may be added here as the platform evolves. The intent is to keep this page short — only the 2–3 settings that meaningfully differ between analysts on the same team.

---

## System Baseline Reference Table

Pre-loaded starting values before any org or user has configured their settings. Implementation agent should seed these as a constants dict in `app/settings/defaults.py` and optionally as seed rows in `org_settings` with `org_id = NULL` to serve as the fallback layer.

| field_key | System Baseline | Unit |
|-----------|-----------------|------|
| `operation_reserve_months` | 6 | months |
| `debt_sizing_mode` | `gap_fill` | enum |
| `amort_term_years` | 30 | years |
| `hold_term_years` | 7 | years |
| `dscr_min` | 1.25 | ratio |
| `ltv_pct` | 70.0 | % |
| `carry_type_construction` | `io_only` | enum |
| `carry_type_permanent` | `pi` | enum |
| `stabilized_occupancy_pct` | 95.0 | % |
| `bad_debt_pct` | 1.0 | % |
| `escalation_rate_pct_annual_income` | 3.0 | % |
| `escalation_rate_pct_annual_opex` | 3.0 | % |
| `noi_escalation_rate_pct` | 3.0 | % |
| `income_mode` | `revenue_opex` | enum |
| `lease_up_curve` | `linear` | enum |
| `lease_up_curve_steepness` | 5 | 1–10 |
| `lease_up_floor_pct` | 50.0 | % |
| `construction_floor_pct` | 40.0 | % |
| `capex_reserve_per_unit_annual` | 250.00 | $/unit/yr |
| `asset_mgmt_fee_pct` | 0.5 | % |
| `management_fee_pct` | 5.0 | % EGI |
| `risk_free_rate_pct` | 4.25 | % |
| `selling_costs_pct` | 2.0 | % |
| `lp_split_pct` | 80.0 | % |
| `gp_split_pct` | 20.0 | % |
| `irr_hurdle_pct_tier1` | 8.0 | % |
| `pref_return_rate_pct` | 6.0 | % |
| `use_line_timing` | `first_day` | enum |
| `loan_closing_origination_pct` | 1.0 | % of loan |
| `loan_closing_legal_flat` | 7500.00 | $ |
| `loan_closing_title_pct` | 0.25 | % of loan |

---

## Implementation Phases

### Phase 1 — Schema & Resolution Engine
*Prerequisite for all other phases.*

1. Create `org_settings` table (schema above) with Alembic migration
2. Create `user_settings` table with Alembic migration
3. Create system baseline constants in `app/settings/defaults.py` (all rows from System Baseline Reference Table)
4. Implement `resolve_default(field_key, user_id, org_id)` utility function in `app/settings/`
5. Define `ORG_SET_FIELDS` constant (list of field keys that bypass user override)
6. Surface `selling_costs_pct` as `OperationalInputs.selling_costs_pct` — remove hardcoded engine constant and wire through `resolve_default`
7. Verify resolution order via unit tests: User-Default → Org-Default → System Baseline → None

**`ORG_SET_FIELDS` initial contents:**
- `operation_reserve_months`
- `debt_sizing_mode`
- `capex_reserve_per_unit_annual`
- `risk_free_rate_pct`

### Phase 2 — API Layer
*Depends on Phase 1.*

8. `GET /api/settings/org` — returns all org settings (admin only)
9. `PUT /api/settings/org/{field_key}` — update single org setting (admin only); constraint validation stub (no enforcement yet)
10. `GET /api/settings/user` — returns current user's settings
11. `PUT /api/settings/user/{field_key}` — update single user setting
12. `GET /api/settings/resolve` — returns the resolved value for a `field_key` given current user/org context (used by model form to pre-fill)

### Phase 3 — Model Form Integration
*Depends on Phase 2. Can run parallel to Phase 4.*

13. On scenario/deal creation, call `resolve_default` for every applicable field and pre-populate form fields
14. Mark Org-Set fields as `readonly` in UI (visual indicator: lock icon or distinct background color)
15. No other UI changes required — form submission path unchanged

### Phase 4 — Settings UI
*Depends on Phase 2. Can run parallel to Phase 3.*

16. Org Admin settings page: render the 7 collapsible groups defined in the Settings UI Layout section above; Underwriting Policy expanded by default
17. User settings page: render the "My Underwriting Preferences" group, expanded by default
18. Constraint display: if `constraint_type` is populated on a row, show allowed range or options as hint text below the input

### Phase 5 — Constraint Enforcement (future — deferred)
*Depends on Phase 4. Do not implement until explicitly initiated.*

19. Populate `constraint_type`, `constraint_min/max`, `constraint_options` on `org_settings` rows per the Future Constraint column in the field tables above
20. Update `PUT /api/settings/org/{field_key}` to enforce constraint on the value being saved
21. Update model form to enforce constraint on in-model edits for Org-Default fields
22. Surface validation errors clearly: e.g., "This value must be between 1.15 and 1.35 per your organization's policy"

---

## Verification Checklist

1. **Unit tests** (`tests/`): Resolution order — confirm user setting wins over org, org wins over system baseline, Org-Set bypasses user setting entirely
2. **API tests**: All 5 settings endpoints return correct values and respect auth (admin gate on org endpoints)
3. **Model pre-fill test**: Create new scenario; confirm all applicable fields pre-fill with correct resolved values
4. **Org-Set lock test**: Confirm `capex_reserve_per_unit_annual`, `operation_reserve_months`, `risk_free_rate_pct`, and `debt_sizing_mode` render as `readonly` in the model form and cannot be edited by a non-admin user
5. **Org-Default edit test**: Confirm `dscr_min`, `selling_costs_pct`, `lp_split_pct`, and other Type 2 fields pre-fill from org settings but remain editable in-model
6. **Regression**: Existing deals with explicitly-entered values are not overwritten by this feature (defaults only apply to new/empty fields at creation time)
7. **Smoke check** on `viciniti.deals` after deploy: create deal, verify pre-fill behavior matches system baselines

---

## Scope Boundaries

**Included in this initiative:**
- `org_settings` and `user_settings` tables
- Resolution utility function and `ORG_SET_FIELDS` constant
- System Baseline constants in `app/settings/defaults.py`
- API endpoints for reading/writing settings
- Model form pre-fill on scenario/deal creation
- Org-Set field locking in UI
- Surfacing `selling_costs_pct` as a configurable `OperationalInputs` field (currently hardcoded in engine)
- Constraint-aware storage schema (nullable columns — no enforcement yet)

**Excluded from this initiative:**
- Constraint enforcement logic (Phase 5 — deferred)
- Per-property-type defaults (future upgrade path — no schema change required to add later)
- Geography-specific defaults (KNN handles market values)
- Scenario template pre-population of OpEx lines (separate feature)
- `target_yoc_pct` org benchmark field (tracked in Open Items)
- Onboarding flow for new orgs configuring their initial settings

---

## Open Items / Follow-On Work

1. **Target YoC benchmark**: No stored ORM field exists today. Adding `target_yoc_pct` to `OperationalInputs` (or as a pure `org_settings` row) enables go/no-go screening indicators in the model UI — e.g., highlight when yield-on-cost falls below the org threshold. Medium-effort; separate initiative. System Baseline: 5.5%.

2. **OpEx line templates**: A "standard MF expense lines" template (management fee, insurance, utilities, maintenance, property tax placeholder) pre-populated on scenario creation would save analyst time and is the correct mechanism for the management fee Org-Default. Separate feature; coordinates with this plan's Org-Default for `management_fee_pct`.

---

*This document was authored as a specification for an implementation agent. The constraint-aware storage schema (Phase 5) is intentionally deferred — all schema columns should be created but no constraint validation logic should be written until Phase 5 is explicitly initiated.*
