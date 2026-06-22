# Excel Export v3 — Surface Recent Engine Work

## Context

Four major financial-modeling areas shipped extensive changes in the
~7 days leading up to 2026-06-03, but the investor workbook export
(`app/exporters/investor_export.py`) does not yet surface them. Result:
the exported xlsx silently under-reports or over-reports several
numbers and entirely omits new sources, balances, and caps.

Captured by completed feature plans:

- `unified-period-engine.md` — engine-internal; cashflow value shapes
  unchanged but reserve sizing now uses period-engine outputs.
- `waterfall-tier-ui-phase5e-handoff.md` — waterfall named-range work
  shipped; nothing left on the export side here.
- `float-earnings-phase-b.md` — new `OperationalOutputs.dev_fee_balance_series`
  (monthly Deferred Dev Fee balance) + DDF paydown waterfall tier.
- `developer-fee-multi-source.md` — per-source `fee_terms`, separate
  Acquisition Fee UseLine, 11-bucket basis inclusions, milestone
  release schedule, deal-type variants (`separate_fee` / `split_rate`
  / `excluded`).

Plus reserves refactor commits (`078d48a`, `499c169`, `5fa90dc`,
`e171078`, `624210b`, `4a4283c`, `90298d9`, etc.):

- Lease-Up Reserve **merged into** Interest Reserve (LUR row gone).
- **Operating Deficit Reserve (ODR)** — new first-class UseLine,
  lease-up-curve-driven.
- **Cash Flow Support Reserve** — auto-emit path removed; manual /
  per-scenario-allowlist only; persisted via bank-account proof.
- Bank-account solvency proof now persisted to
  `OperationalOutputs.bank_account_proof`.

### Concrete user-visible bug today

For the anemic-construction scenario, exported S&U was showing
Operating Reserve ≈ $97k against DB $470k (fixed in commit `2efa6fb`,
2026-06-03). Similar export-vs-engine divergences exist for the new
ODR, Cash Flow Support Reserve, DDF balance, dev fee caps, and float
earnings. v3 closes the entire gap.

### Goal

After v3, exporting any scenario produces a workbook whose Y1 P&L,
S&U, Cash Flow, and Summary numbers all match the engine values
within $1, AND surfaces the new structured data (dev fee caps,
release schedule, DDF balance, float earnings, bank-account cushion)
in human-readable form.

---

## Existing Exporter Map (don't re-read while planning)

`export_investor_workbook` (lines 122–262) wires these section
builders. v3 modifies most of them:

| Builder | Line | Sheet | v3 touch |
|---|---|---|---|
| `_build_cover` | 715 | Cover | — |
| `_build_uw_summary` | 1310 | Underwriting Summary | **+ Bank-account proof KPI** |
| `_build_uw_proforma` | 2102 | Underwriting Pro Forma | — |
| `_build_uw_cashflow` | 2602 | Underwriting Cash Flow | **+ DDF Balance + DDF Recovered rows; + Float Earnings injection row** |
| `_build_su_sheet` | 5756 | Sources & Uses | **+ ODR row; + Cash Flow Support Reserve row (when present); + separate Acquisition Fee row; + Float Earnings Source row; + Dev Fee Caps block; LUR row removed** |
| `_build_investor_returns` | 3074 | Investor Returns | — |
| `_build_waterfall_sheet` | 3814 | Waterfall | — (DDF tier already at 3674) |
| `_build_assumptions` | 5297 | Assumptions | **+ acquisition_fee_pct, dev_fee_acquisition_pct, milestone_weights, holdback inputs; + T-bond yield (float earnings) input** |
| `_build_debt_schedule` | 4674 | Debt Schedule | — |
| `_build_glossary` | 6023 | Glossary | **+ definitions for ODR, CFSR, DDF Balance, Float Earnings, Acquisition Fee** |

---

## Schema Additions to Surface

| Field | File | Line | Shape |
|---|---|---|---|
| `OperationalOutputs.dev_fee_balance_series` | `app/models/cashflow.py` | 153 | `{"opening_at_close": Decimal, "periods": [{"period", "monthly_earnings", "closing_balance"}], "fully_paid_period": int \| None}` |
| `OperationalOutputs.float_earnings_series` | `app/models/cashflow.py` | 146 | `{"sources": [{"float_source_id", "parent_module_id", "total_earnings", ...}]}` |
| `OperationalOutputs.bank_account_proof` | `app/models/cashflow.py` | 138 | `{"max_shortfall_date", "is_solvent", "co_period", "stabilized_period", "months_simulated"}` |
| `CapitalModule.fee_terms` (JSONB) | `app/models/capital.py` | 81 | `{"max_pct", "per_unit_cap", "absolute_cap", "basis_inclusions_override": [...], "basis_exclusions": [...], "regulated", "notes"}` |
| `UseLine.dev_fee_binding_context` | `app/models/deal.py` | 823 | `{"binding_source", "per_source_allowance": {...}, "headroom": Decimal}` |
| `UseLine.dev_fee_release_schedule` | `app/models/deal.py` | 812 | `{"milestone_1": {weight, holdback}, ...}` |
| `UseLine.is_auto_acquisition_fee` | `app/models/deal.py` | 833 | `bool` |
| `_BALANCE_ONLY_LABELS` frozenset | `app/engines/cashflow.py` | 110 | **missing "Operating Deficit Reserve" + "Cash Flow Support Reserve"** (only present in local set at line 2628) |

---

## Slice Plan

### Slice 1 — Reserves cleanup (ship first)

Fixes a real number error: ODR currently inflates Total Project Cost
on UW Summary because the exporter imports `_BALANCE_ONLY_LABELS` from
`cashflow.py:110`, which is missing ODR + Cash Flow Support Reserve.

**Changes:**

1. **Engine** (`app/engines/cashflow.py:110`) — add `"Operating Deficit Reserve"` and `"Cash Flow Support Reserve"` to the module-level frozenset. Eliminate the local redefinition at line 2628 in favor of the module-level set. Engine + exporter agree.
2. **Exporter** (`app/exporters/investor_export.py` around 5756, 5832) — render ODR row when present, with named cell `s_odr_amount`; render Cash Flow Support Reserve row when present, with named cell `s_cfsr_amount`. Both flagged as balance-only so they don't double-count into TPC. Remove LUR-specific comments / handling (LUR row no longer emitted).
3. **UW Summary** (`_build_uw_summary` around 1310) — add Bank-account proof KPI tile: lowest-cash month label + dollar cushion. Read from `OperationalOutputs.bank_account_proof`. Render em-dash when null.
4. **Glossary** — add ODR, CFSR, Bank-account proof definitions.

**New parity tests** (`tests/exporters/`):

- `test_su_odr_row_balance_only_excluded_from_tpc.py` — seed scenario with non-zero ODR; assert TPC on UW Summary excludes ODR amount within $1.
- `test_uw_summary_bank_account_proof_kpi.py` — seed solvent + insolvent fixtures; assert KPI cell shows correct cushion value, em-dash when proof is null.

---

### Slice 2 — Deferred Dev Fee + Float Earnings

**Changes:**

1. **Cash Flow sheet** (`_build_uw_cashflow` 2602) — two new rows:
   - "Deferred Dev Fee Balance" — reads `OperationalOutputs.dev_fee_balance_series.periods[m].closing_balance` per period. Named range `r_uw_cf_ddf_balance`.
   - "Deferred Dev Fee Recovered" — per-period recovery (closing − opening − accrual). Named range `r_uw_cf_ddf_recovered`.
   - "Float Earnings (Found Money)" — sums per-period `float_earnings_series.sources[*].monthly_earnings`. Named range `r_uw_cf_float_earnings`.
2. **S&U Sources block** (`_build_su_sheet` around 5756) — add "Deferred Dev Fee" source row when a `deferred_developer_fee` CapitalModule exists. Add "Float Earnings (Found Money)" source row when `float_earnings_series` is populated.
3. **Assumptions** (`_build_assumptions` 5297) — add T-bond yield rate + Day-1 draw window input cells. Names: `s_float_earnings_yield_pct`, `s_float_earnings_draw_window_days`.
4. **Glossary** — DDF Balance, Float Earnings.

**Tests:**

- `test_uw_cashflow_ddf_balance_row.py` — assert monthly balance row matches `dev_fee_balance_series` within $1 per period.
- `test_su_sources_float_earnings.py` — Float Earnings appears as a Source when engine emits it.

---

### Slice 3 — Dev Fee multi-source + Acquisition Fee

**Changes:**

1. **S&U Uses block** (`_build_su_sheet` 5832-ish) — when a UseLine has `is_auto_acquisition_fee=True`, render it under the Acquisition cost section instead of Soft Costs. Named cell `s_acquisition_fee`.
2. **New "Dev Fee Caps" block on S&U** — directly below the Dev Fee UseLine, one row per CapitalModule with `fee_terms`. Columns: Source name, max %, per-unit cap, absolute cap, allowable $, binding (✓/—). Bold the binding row. Read binding indicator from `UseLine.dev_fee_binding_context.binding_source`. Named range `r_su_dev_fee_caps`.
3. **Assumptions** — add cells for `acquisition_fee_pct`, `dev_fee_acquisition_pct`, `dev_fee_final_holdback_pct`. Milestone weights JSON serialized to a small inline table.
4. **Dev Fee Release Schedule mini-block on S&U** — one row per milestone showing weight % + holdback % from `UseLine.dev_fee_release_schedule`. Skip when empty.

**Tests:**

- `test_su_acquisition_fee_in_acquisition_block.py` — assert is_auto_acquisition_fee UseLines land under Acquisition, not Soft Costs.
- `test_su_dev_fee_caps_block.py` — seed two modules with different fee_terms; assert caps block renders both, binding row marked.

---

### Slice 4 — Engine-side capital events on S&U

**Surfaced during Slice 1 prod validation** (2026-06-03). For deal
`cf0e77c3` the Excel TPC formula computed $13,311,629 (sum of
UseLines minus balance-only) while the DB engine TPC was
$13,614,673 — a $303,044 gap that traces to capital_event line
items the engine writes during sizing (loan fees, closing costs
from `_DEFAULT_LOAN_COSTS`, etc.) that never get rendered as
UseLine rows on S&U.

Same root cause as the Operating Reserve parity bug fixed in
commit `2efa6fb`: a UseLine-vs-engine-capital_event divergence.

**Changes:**

1. **Exporter** (`_build_su_sheet` around 5832) — after iterating
   `use_lines_by_project`, walk `ctx.cashflow_line_items` filtered
   to `capital_event` direction != inflow that are NOT already
   represented by a UseLine (dedup on label + amount). Render each
   as a row under Soft Costs (or a new "Engine-Derived Costs"
   subsection) so Total Uses matches engine TPC.
2. **Investigate first** — confirm whether closing costs SHOULD
   be UseLines (engine-side bug to fix) or whether the exporter
   should consume both inputs (rendering bug). Engine fix is
   cleaner long-term but riskier.

**Tests:**

- `test_su_tpc_matches_engine_tpc.py` — seed scenario with a
  debt module that produces `_DEFAULT_LOAN_COSTS`; assert Excel
  TPC formula equals `OperationalOutputs.total_project_cost`
  within $1.

---

## Pattern Reuse

These existing patterns in `investor_export.py` should be reused —
no new abstractions needed:

- **CellRegistry pattern** (named cell registration) — already used everywhere; same call for new cells.
- **`_kv_row_optional`** — em-dash when None pattern; reuse for bank-account proof KPI.
- **`_BALANCE_ONLY_LABELS` import** — same import line in exporter; just gets bigger.
- **Section-label + header-row helpers** (used in `_build_su_sheet`) — reuse for Dev Fee Caps mini-block.
- **`_aggregate_scenario_annual`** (line 1000) — sums monthly CashFlow rows into annual buckets; reuse for any new annual roll-up.

No new utility files needed.

---

## Verification

### Unit / integration

Per-slice tests above. Run after each slice:

```bash
cd ../vicinitideals-worktrees/excel-export-v3
PYTHONPATH="$(pwd)" uv run --project ../../vicinitideals pytest tests/exporters/ -v
```

Should stay at zero regressions throughout (currently 303 passing).

### End-to-end smoke against production scenarios

For each slice, export the live scenarios that motivated the work
and confirm numbers match the Builder UI:

- **Slice 1** — anemic-construction (`cf0e77c3`): TPC matches engine within $1 even though ODR is non-zero.
- **Slice 2** — Brittany Place (`c05b7b56`): DDF balance row matches `OperationalOutputs.dev_fee_balance_series`; Float Earnings row matches engine.
- **Slice 3** — any scenario with a `value_add` deal type + two debt sources with different `fee_terms`: Acquisition Fee lands in Acquisition block; caps block renders both modules; binding row marked.

### Deploy + production verification

Standard 3-step deploy after each slice:

```bash
git push origin main
mcp__proxmox-mcp__ssh_exec container_id=114 command="bash /root/deploy-vicinitideals.sh"
```

Production smoke: re-export the motivating scenario via
`docker exec vicinitideals-api python /tmp/_smoke.py` (same pattern
used for the Operating Reserve fix earlier today) and confirm the
new cells render the expected values.

### Documentation updates

After Slice 3 ships, update `docs/FINANCIAL_MODEL.md` Appendix H
(Multi-Source Developer Fee — already exists from commit `2c3984c`)
to cross-reference the new Excel surface, and add an "Export" section
to `developer-fee-multi-source.md` noting what's now in the workbook.
