# Investor Excel Export — Formula Conversion Plan

**Status:** Draft (2026-05-21). Builds on the completed v2 plan at
[`Completed/investor-excel-export-v2.md`](./Completed/investor-excel-export-v2.md),
which intentionally deferred formula work to "Phase 2." That deferral
is what this doc fills in.

**Audience:** an agent or contributor who will execute this from scratch.
Treat the v2 doc as historical context for the workbook's structure and
naming conventions; treat this doc as the source of truth for everything
formula-related, the assumption-surface expansion, and the
single-project consolidation.

---

## 1. Goal & Non-Goals

**Goal.** Convert every output cell in the investor workbook from a
hard-coded engine value to an Excel formula that traces back to a named
input cell. After conversion, an LP / lender should be able to:

1. Change an assumption (rate, term, exit cap, growth rate, etc.) in the
   Assumptions sheet
2. Press F9 (or rely on auto-calc)
3. See every downstream sheet — Pro Forma, Cash Flow, Investor Returns,
   Waterfall, Debt Schedule, Sensitivity — update without re-running the
   server engine

**Goal 2.** Close the **debt-assumption gap** on the Assumptions sheet.
Today only Principal + Rate are surfaced per capital module. Term, IO
months, amort years, points, exit fee, prepay, DSCR cap, and LTV cap
are persisted in `CapitalModule.source` / `.carry` JSONB but invisible
to the workbook user, which is the largest single reason formulas
can't yet drive carry costs.

**Goal 3.** Consolidate single-project workbooks. When a Scenario has
exactly one Project, the standalone `P1 {Name}` sheet is redundant
with the Underwriting sheets. Merge them.

**Non-goals.**

- **No Excel-Solver / Goal-Seek workflows.** Anything the engine
  computes via Newton-Raphson (DSCR-capped sizing) stays engine-side;
  Excel reads the result as an input value, not a re-solvable cell.
  Documented in §6.
- **No iterative-calculation requirement.** The self-referential
  draw-schedule solve (`app/engines/draw_schedule.py`) is held flat in
  Excel: draw amounts per period are emitted as engine outputs and
  formulas downstream reference them. Re-solving requires the engine.
  Rationale in §6.
- **No replacement of the engine.** The engine remains the source of
  truth at export time. Excel formulas reproduce engine math for
  user-edit responsiveness, not for primary computation. Bidirectional
  parity test (§8) enforces this on every export.
- **No new sheet structure.** Sheet order, named-range convention, and
  the v2 §6 `CellRegistry` pattern all carry forward unchanged.

---

## 2. Current State Snapshot (as of 2026-05-21)

Since v2 was marked Completed, the workbook has grown to **16 sheet
builders across 4 profiles** (`internal`, `lp`, `lender`, `proforma`).
Reproduced from a fresh inventory of
[`app/exporters/investor_export.py`](../../app/exporters/investor_export.py):

| # | Sheet | Builder | Profiles | Formula candidate? |
|---|---|---|---|---|
| 1 | Cover | `_build_cover` | all | partial — header values + Sources-Gap |
| 2 | Underwriting Summary | `_build_uw_summary` | internal/lp/lender | **yes — heavy** |
| 3 | Underwriting Pro Forma | `_build_uw_proforma` | internal/lp/lender | **yes — heavy** |
| 4 | Underwriting Cash Flow | `_build_uw_cashflow` | internal/lp/lender | **yes — heavy** |
| 5 | Investor Returns | `_build_investor_returns` | internal/lp | **yes — IRR/XIRR via formula** |
| 6 | Waterfall | `_build_waterfall_sheet` | internal/lp | **yes — tier math** |
| 7 | Sources & Uses | `_build_su_sheet` | all | **yes — sum formulas** |
| 8 | Unit Mix | `_build_unit_mix_sheet` | all | partial — count/weight sums |
| 9 | Sensitivity | `_build_sensitivity` | internal/lp | **yes — Excel Data Table** |
| 10 | Debt Schedule | `_build_debt_schedule` | all | **yes — PMT/IPMT/PPMT** |
| 11 | Assumptions | `_build_assumptions` | internal/lender | input-only — expand §3 |
| 12 | Pro Forma (combined) | `_build_proforma_combined` | proforma | already formula-driven |
| 13 | Cover (proforma) | reuses `_build_cover` | proforma | n/a |
| 14 | Glossary | `_build_glossary` | all | n/a — doc-driven |
| 15 | Per-Project sheets | `_build_project_sheet` | all | **yes — see §5 consolidation** |
| 16 | Version Tab | `_build_version_tab` | all | n/a — metadata |

**Sheets that already use formulas:** only the `proforma` profile's
combined Pro Forma sheet pulls cells from per-project sheets via `=`
references. Every other sheet writes engine outputs as raw `Decimal`
values.

---

## 3. Assumptions Sheet: Expansion

Today's Assumptions sheet has three blocks (A scenario, B per-project,
C capital stack). Formula conversion forces every assumption that
drives a downstream formula to be a **single source named cell**.

### 3.1 Gap analysis vs current state

**Block A — Scenario-level.** Today:

- `s_assumptions_scenario_name`, `s_assumptions_noi_basis`,
  `s_assumptions_project_type` (display only)
- `s_hold_years` (input)
- `s_exit_cap_rate` (input)
- `s_opex_growth_rate` (input)
- `s_operating_reserve_months` (input)
- `s_initial_occupancy` (input)
- `s_asset_mgmt_fee` (input)

Missing inputs that downstream formulas would need:

- `s_revenue_growth_rate` — `OperationalInputs.revenue_growth_rate_pct_annual`
- `s_vacancy_pct` — `OperationalInputs.vacancy_pct`
- `s_collection_loss_pct` — `OperationalInputs.collection_loss_pct`
- `s_replacement_reserve_per_unit_annual` — for Pro Forma CapEx line
- `s_lease_commission_pct` — leasing commissions if any
- `s_discount_rate` — for DCF NPV (currently engine-only)
- `s_irr_hurdle_*` — waterfall hurdle rates, currently in `WaterfallTier`
  rows, but if Waterfall sheet pulls these into formulas they need
  named-range backing
- `s_going_in_cap_target` — only if the Cap-Spread KPI is to become
  a formula (`s_cap_spread = s_going_in_cap - s_exit_cap_rate`)

**Block B — Per-project.** Today: acquisition price, unit counts,
in-place/market rent, stabilized occupancy, going-in cap, exit cap,
construction months, lease-up months. Largely complete for the rent +
expense math, but missing:

- `p{n}_replacement_reserve` — if it ever overrides the scenario default
- `p{n}_renovation_cost_per_unit` — currently rolled into UseLines only
- `p{n}_acquisition_close_period` — Pro Forma Y0/Y1 split depends on this

**Block C — Capital stack. This is the single largest gap.** Today
each module row shows: Label, Funder Type, Principal, Rate,
Auto-Sized?, Covers. Every other carry-driving field is hidden.

To make the Debt Schedule + Cash Flow + UW Cash Flow sheets respond to
edits, Block C must expand to one column per carry-driving field. Add:

| Column | Source field | Used by |
|---|---|---|
| Term (years) | `source.term_years` | Debt Schedule amort, Cash Flow exit |
| IO months | `carry.io_months` | Carry-type IO period |
| Amort years | `source.amort_years` | PMT period count |
| Points (upfront fee) | `source.points_pct` | S&U + Y0 outflow |
| Exit fee | `source.exit_fee_pct` | Exit-period cash flow |
| Prepayment penalty | `source.prepayment_penalty_pct` | Refi-event modeling |
| DSCR cap (target) | `source.dscr_floor_pct` | Display only — see §6 |
| LTV cap | `source.ltv_cap_pct` | Display only — see §6 |
| Day count | `source.day_count` | Interest-reserve / capitalized-interest math |
| Carry type | `carry.carry_type` | Selector for which formula bank to use |

Naming pattern stays consistent: `s_module_{m}_principal`,
`s_module_{m}_rate`, `s_module_{m}_term_years`, etc., where `{m}` is
the module's ordinal in the Capital Stack block.

### 3.2 Architecture decision: one sheet or per-page assumptions?

**Recommendation: keep one Assumptions sheet, expand Block C.**

The v2 plan picked a single Assumptions sheet for a reason — it
matches how every reference investor model (HelloData, Apartment
Acquisition Model) lays out assumptions, and it gives the user a
single place to scan + edit. Scattering assumptions per-sheet sounds
faster but breaks the convention LPs expect and forces them to hunt.

Concrete layout:

```
Block A  rows  1– 25     scenario scalars (12–15 inputs)
Block B  rows 27– 50     per-project metrics (project columns)
Block C  rows 52– 75+    capital stack (one row per module, ~14 cols)
Block D  rows 77+        waterfall hurdles + promote tiers
```

Block D is new (formerly inline on the Waterfall sheet). It exposes
the tier table — pref rate, catchup share, promote share — so formula
work on the Waterfall sheet has named cells to reference.

### 3.3 Visual / discipline

- All cells in Blocks A/C/D and the editable rows of B are formatted
  with the **blue-input** convention already established in H3 (commit
  `24f6e5a`). No formula text in input cells, ever.
- Each row's named-range is registered on the Assumptions sheet *only*.
  No other sheet may register a competing name for the same value.

---

## 4. Formula Bank by Sheet

For each output sheet, this is the conversion strategy.

### 4.1 Underwriting Pro Forma (rows = line items, cols = Y0–Y10)

Math today (engine) → math in Excel:

| Line | Formula pattern |
|---|---|
| Gross Revenue (Y_n) | `= Gross Revenue (Y_n-1) * (1 + s_revenue_growth_rate)` for n ≥ 2; Y1 = base = unit count × market rent × 12 |
| Vacancy | `= - Gross Revenue * s_vacancy_pct` |
| EGI | `= Gross Revenue + Vacancy` (vacancy negative) |
| OpEx categories | `= OpEx (Y_n-1) * (1 + s_opex_growth_rate)` |
| NOI | `= EGI - SUM(OpEx categories)` |
| Replacement Reserve | `= - s_replacement_reserve_per_unit_annual * p{n}_unit_count` |
| Asset Mgmt Fee | `= - EGI * s_asset_mgmt_fee` |
| Stabilized NOI | `= NOI - Replacement Reserve - Asset Mgmt Fee` |

Year-0 / acquisition-period handling: Y0 is a partial year in most
cases. Use `IF(year_index = 0, partial-month proration formula, full-year
formula)` so the user editing `s_initial_occupancy` immediately sees
Y0 EGI respond. The proration multiplier itself is named —
`s_y0_months / 12` — to keep formulas readable.

### 4.2 Underwriting Cash Flow

| Line | Formula pattern |
|---|---|
| NOI | `= 'Underwriting Pro Forma'!<NOI Y_n cell>` |
| Debt Service (per loan) | `= 'Debt Schedule'!<debt service Y_n>` |
| Levered CF | `= NOI - Debt Service` |
| Unlevered CF | `= NOI - CapEx` |
| DSCR | `= NOI / Debt Service` |
| Cumulative LCF | `= Cum LCF (Y_n-1) + Levered CF Y_n` |
| Exit-year sale proceeds | `= 'Underwriting Summary'!s_exit_value` |
| Exit-year debt payoff | `= 'Debt Schedule'!<balance at exit>` |

### 4.3 Debt Schedule — the largest formula surface

For each capital module: one block per loan, columns Period 0…N.

| Carry type | Period-N formula |
|---|---|
| `pi` (amortizing) | Standard `PMT` / `IPMT` / `PPMT` against `s_module_{m}_rate`, `s_module_{m}_amort_years`, `s_module_{m}_principal` |
| `io_only` (true IO) | Interest = `balance * rate / 12 * day_count_factor`; principal stays flat |
| `interest_reserve` | Average-draw factor: `interest = (draws_to_date / 2) * rate / 12` for the active window; switches to amortizing post-construction |
| `capitalized_interest` (PIK) | Balance grows: `balance_N = balance_(N-1) * (1 + rate/12)`; debt service = 0 during PIK window |

Day-count handling: a named cell `s_module_{m}_day_count` resolves to
1 (30/360) or `DAYS(period_end, period_start)/365` for actual-360 /
actual-365.

**Active-window logic.** Each module has an `active_from_milestone_id`
that defines when debt service starts. In Excel: use an `IF` against
the period column header (numeric month index) compared against a named
`s_module_{m}_active_start_month` cell. Out-of-window periods → 0.

### 4.4 Investor Returns

| Cell | Formula |
|---|---|
| LP IRR | `= IRR(LP cash flow column)` or `XIRR(values, dates)` if dates are explicit |
| LP Equity Multiple | `= SUM(positive LP distributions) / -SUM(negative LP contributions)` |
| LP CoC Y1 | `= LP CF Y1 / -LP CF Y0` |
| GP IRR | same pattern against GP column |
| GP Promote $ | from Waterfall sheet's tier outputs |

### 4.5 Waterfall

Tier-by-tier formulas. For each tier:

- LP-preferred return accrual: `= LP balance * s_irr_hurdle_tier1` per period
- Distribution split: `IF(tier_unmet, all to LP, split per s_promote_tier1)`
- Tier roll-forward: `LP balance (Y_n+1) = LP balance (Y_n) + preferred accrual - LP distribution`

This is where the most formula testing pays off — waterfalls are where
LPs spot errors first.

### 4.6 Sources & Uses

Pure sums. Each Use line totals its phase column; each Source line
totals from `s_module_{m}_principal`. Bottom Sources = Uses parity
becomes a single formula: `= s_total_sources - s_total_uses`, named
`s_su_gap`, conditionally formatted red when non-zero.

### 4.7 Cover

Header values become cross-sheet references:

- `Total Project Cost` cell = `='Sources & Uses'!s_total_uses`
- `Equity Required` cell = `='Sources & Uses'!s_total_equity`
- `Stabilized NOI` = `='Underwriting Pro Forma'!s_noi_stabilized`
- `Stabilized DSCR` = `MIN('Debt Schedule'!<per-loan DSCR cells>)`
- `Combined Levered IRR` = `='Investor Returns'!s_lp_irr`

Sources-Gap banner formula stays — already a formula.

### 4.8 Sensitivity

Excel **Data Tables** (`Table` formula) are the right tool: pick two
input cells (exit cap, stabilized occupancy), point at one output
formula (LP IRR), Excel fills the grid. Migration: replace the engine's
sensitivity grid with a `TABLE(row_input, col_input)` array formula
that references `s_exit_cap_rate` and `s_stabilized_occupancy`.

Caveat: Data Tables only work if every formula in the dependency chain
is in-workbook. So this sheet can't be migrated until **every other
sheet** is formula-driven.

### 4.9 Unit Mix, Glossary, Version Tab

- **Unit Mix.** Sum columns (total units, weighted avg rent) become
  `SUMPRODUCT` formulas referencing the per-row inputs.
- **Glossary.** No conversion — doc-driven.
- **Version Tab.** No conversion — metadata.

---

## 5. Single-Project Consolidation

User requirement: when `len(deal_projects) == 1`, the dedicated
`P1 {Name}` sheet duplicates everything on the Underwriting sheets.
Merge them.

### 5.1 Behavior

- `len(projects) == 1`: emit `Underwriting Summary`, `Underwriting Pro
  Forma`, `Underwriting Cash Flow` — and **omit** the `P1 {Name}`
  sheet entirely. Any data unique to P1 (project location, deal type,
  proposed-use specifics, per-project S&U breakdown) is appended to
  the Underwriting sheets in a labeled section.
- `len(projects) >= 2`: behavior unchanged. Underwriting sheets sum
  across projects; each project gets its own `P{n}` sheet.

### 5.2 Per-project data to fold in (single-project case)

From the current per-project sheet, anything *not* already shown on
the Underwriting sheets:

- **Project header.** Location, deal type, project status pill →
  appended below the title block on Underwriting Summary.
- **Project S&U block.** When there's only 1 project, the scenario S&U
  *is* the project S&U; the dedicated Sources & Uses sheet covers it.
  No duplication needed.
- **Hyperlinks back to Summary.** Removed (no per-project sheet to
  navigate to).

### 5.3 Named-range implications

In single-project mode, `p1_*` ranges still exist (the parity validator
in §8 depends on them) but they resolve to cells on the Underwriting
sheets, not a dedicated P1 sheet. The `CellRegistry` is the right place
to handle this — when the registry is told `register("p1_acquisition_price",
"Underwriting Summary", row, col)` instead of `("P1 Liberty", ...)`, the
defined name still resolves correctly and no downstream formula breaks.

### 5.4 Naming

Sheet names in single-project mode:

```
1. Cover
2. Underwriting Summary
3. Underwriting Pro Forma
4. Underwriting Cash Flow
5. Sources & Uses
6. Investor Returns
7. Waterfall
8. Debt Schedule
9. Unit Mix
10. Sensitivity
11. Assumptions
12. Glossary
```

No `P1` sheet. Multi-project workbooks continue to add `P1 {Name}`,
`P2 {Name}`, etc. after Assumptions, before Glossary.

---

## 6. Out-of-scope: items the engine still owns

Three classes of math cannot be cleanly expressed in workbook
formulas. The plan calls these out so reviewers know what *won't*
respond to a cell edit.

### 6.1 DSCR-capped debt sizing

The engine's `_auto_size_debt_modules` runs Newton-Raphson via
`solve_principal_for_dscr` to find the principal that produces a
target DSCR. There's no clean Excel formula for this. Two options:

- **Picked (default):** Auto-sized principal is written as a **value**
  in `s_module_{m}_principal` at export time. The cell is colored blue
  (input-like) but a note in the cell comment says "auto-sized at
  export; edit and re-export to re-solve." The downstream cash flow
  responds to the principal cell, but doesn't itself re-solve DSCR.
- **Alternative:** instruct the user via a cell comment to use Excel
  Goal Seek. Documented in Glossary, not the workflow we expect.

### 6.2 Self-referential draw schedule

`app/engines/draw_schedule.py` solves for closing costs that depend on
the principal that depends on closing costs. Modeled as a fixed-point
iteration in Python. Excel's iterative-calc mode could replicate it
but introduces convergence risk on every recalc.

**Picked:** draw amounts per period are written as engine outputs
(`s_module_{m}_draw_period_N`). Formulas reference them. Editing
inputs does *not* re-run the draw solve; the user has to re-export.
The Sources = Uses parity formula on S&U will surface drift if their
edits invalidate the solve.

### 6.3 Newton-Raphson dependent quantities

`pyxirr` IRR is replaced by Excel's `IRR` / `XIRR` (both ship in Excel
and have no issue). But any *other* iterative solve (debt service to
DSCR target, principal-to-LTV-cap) stays engine-side.

---

## 7. Build Order

### Status (2026-05-22)

| # | Title | Status | SHA |
|---|---|---|---|
| 0 | Audit + parity baseline | shipped | (see branch history) |
| 1 | Assumptions sheet expansion | shipped | (see branch history) |
| 2 | Sources & Uses + Cover formulas | shipped | (see branch history) |
| 3 | Pro Forma EGI + NOI formulas | shipped | `53227af` |
| 4 | Cash Flow derived-row formulas (Levered / Unlevered / DSCR / Cumulative) | shipped | `52a57cd` |
| 5 | Investor Returns Return($) + Combined IRR formulas | shipped | `4842faa` |
| 6 | Debt Schedule Annual P&I (PMT) formula | shipped — narrow | `a69ce0a` |
| 7 | Sensitivity Data Table | **deferred** | openpyxl 3.x cannot emit Excel `TABLE()` array formulas cleanly; sheet stays engine-driven. Revisit when a viable openpyxl array-formula path lands. |
| 8 | Single-project consolidation | shipped | `746c0fc` |
| 9 | Cleanup + doc updates | this commit | — |

**Out of plan-scope but follow-up candidates:**
- Debt Schedule amort table (CUMIPMT / CUMPRINC per year) — adjacent to commit 6 but needs IO-vs-amort branch logic plus end-balance cross-row references.
- Pro Forma / Cash Flow Debt Service rows — would chain back to the new `s_loan_*_annual_pi` named ranges; pending tier-aware allocation.
- ~~Investor Returns Equity Multiple / CoC / weighted IRR — needs new total-committed-equity and total-distributions named ranges.~~ **Shipped in Phase 5d+5e** (`feature/phase5-5d`): `s_lp_distributions_total`, `s_gp_distributions_total` (formula), `s_lp_em`, `s_gp_em` (formula), `s_lp_irr`, `s_gp_irr`, `s_committed_lp_equity`, `s_committed_gp_equity` on Investor Returns.
- ~~Investor Returns LP/GP CoC Year 1 and IRR as live Excel formulas.~~ **Shipped in Phase 5f** (`feature/phase5-irr`): annual LP/GP CF rows (`s_returns_lp_y0..yN`, `s_returns_gp_y0..yN`) emitted on Investor Returns; ranges `r_returns_lp_cf` / `r_returns_gp_cf` registered; `s_lp_irr` / `s_gp_irr` converted to `=IFERROR(IRR(range), fallback)` live formulas; `s_lp_coc_y1` / `s_gp_coc_y1` added as formula cells.

### Commit 0 — Audit + parity baseline (prerequisite)

- Capture the current export's output for a known fixture as the
  baseline.
- Add a parity helper:
  `tests/exporters/_parity_helpers.py::diff_workbook_values(before, after)`
  that returns the set of cells whose values changed.
- The next 4 commits each run this against the baseline; only cells
  on the Assumptions sheet (the new inputs) should differ, and only
  in formatting (value identical, formula `vs` raw value).

### Commit 1 — Assumptions sheet expansion (Block C + new A/D rows)

- Expand `_build_assumptions` to emit the full Block C debt-assumption
  surface (§3.1) and the missing Block A scenario inputs.
- Add Block D waterfall hurdles.
- Register every new named range.
- **No formulas anywhere else yet.** All other sheets keep emitting
  values. Workbook is still hard-coded but the input surface is
  complete.
- Tests: `test_assumptions_block_c_has_all_debt_fields`,
  `test_assumptions_named_ranges_complete` (every input has a name).

### Commit 2 — Sources & Uses + Cover formulas

- Convert S&U row sums and totals to `SUM` / `SUMIFS` formulas
  referencing the per-Use cells and `s_module_{m}_principal`.
- Convert Cover header values to cross-sheet `=` references.
- Tests: `test_su_total_uses_is_formula`, `test_su_recomputes_on_edit`
  (mutate a named cell, re-load workbook, expect totals to shift —
  requires opening with `data_only=False`).

### Commit 3 — Pro Forma + Cash Flow formulas

- Convert UW Pro Forma to growth formulas referencing
  `s_revenue_growth_rate`, `s_opex_growth_rate`, etc.
- Convert UW Cash Flow to formulas referencing Pro Forma cells +
  Debt Schedule cells.
- Tests: parity test asserts that with assumption cells set to the
  same values as the engine input, formula outputs match engine
  outputs to 0.01.

### Commit 4 — Debt Schedule formulas

- Convert each loan block to PMT/IPMT/PPMT formulas referencing
  `s_module_{m}_*` cells.
- Special-case the four carry types per §4.3.
- Tests: per-carry-type parity (`test_debt_schedule_pi_parity`,
  `test_debt_schedule_io_only_parity`, etc.).

### Commit 5 — Investor Returns + Waterfall formulas

- Convert IRR / EM / CoC cells to `IRR` / `XIRR` / `SUM` formulas.
- Convert Waterfall tier accruals + distribution splits to formulas
  referencing `s_irr_hurdle_*` + `s_promote_*`.
- Tests: waterfall parity per tier.

### Commit 6 — Sensitivity Data Table

- Replace engine-driven sensitivity grid with Excel `TABLE()` formula
  referencing `s_exit_cap_rate` + `s_stabilized_occupancy` (or
  whichever two-input pair the existing sheet uses).
- Tests: `test_sensitivity_is_data_table` (assert the cells carry the
  `TABLE` formula, not values).

### Commit 7 — Single-project consolidation

- Implement §5: when `len(projects) == 1`, omit the `P1 {Name}` sheet,
  fold project header data into Underwriting Summary, register `p1_*`
  ranges to Underwriting sheet cells.
- Tests: `test_single_project_omits_p1_sheet`,
  `test_single_project_p1_named_ranges_resolve`,
  `test_multi_project_p1_sheet_still_present`.

### Commit 8 — Cleanup

- Drop any engine-output writes that are now duplicated by formulas.
- Update [docs/FINANCIAL_MODEL.md](../FINANCIAL_MODEL.md) glossary
  entries to note "formula-driven in export" where applicable.
- Update glossary parser if any new audience-tagged metrics were
  added.

Each commit ships independently — the workbook stays openable and
test-passing at every step. After commit 1 the surface is editable
but doesn't recompute; after commit 5 every KPI on the UW + Returns
+ Waterfall sheets responds to edits; after commit 7 single-project
deals have the simplified layout.

---

## 8. Tests

In addition to the per-commit tests above, two cross-cutting tests
guard the conversion:

### 8.1 Parity test — engine vs formulas

`tests/exporters/test_investor_export_formula_parity.py`:

```python
async def test_every_formula_cell_matches_engine_output(seeded_scenario):
    wb_bytes = await export_investor_workbook(scenario_id, session)
    wb = load_workbook(BytesIO(wb_bytes), data_only=True)  # computed values
    engine_outputs = await compute_full_engine_view(scenario_id, session)
    for sheet_name, cell, named_range in EXPECTED_FORMULA_CELLS:
        excel_value = wb[sheet_name][cell].value
        engine_value = engine_outputs[named_range]
        assert abs(Decimal(excel_value) - engine_value) < Decimal("0.01"), (
            f"{sheet_name}!{cell} ({named_range}) — "
            f"Excel: {excel_value}, engine: {engine_value}"
        )
```

`data_only=True` forces openpyxl to load cached computed values, which
LibreOffice / Excel writes on save. CI runs the export, opens the
workbook in a headless LibreOffice instance to force recalc, then
re-opens with `data_only=True` to read computed values.

### 8.2 Round-trip edit test — formulas respond to input changes

`tests/exporters/test_investor_export_formula_edit.py`:

```python
def test_changing_exit_cap_changes_exit_value():
    wb = load_workbook(export_path)
    wb.defined_names["s_exit_cap_rate"].destinations  # find the cell
    set_cell_value(wb, "s_exit_cap_rate", 0.07)        # was 0.06
    wb.save(tmp_path)
    # Force LibreOffice recalc
    subprocess.run(["libreoffice", "--headless", "--calc",
                    "--convert-to", "xlsx", tmp_path], check=True)
    wb2 = load_workbook(tmp_path, data_only=True)
    new_exit_value = read_cell(wb2, "s_exit_value")
    assert new_exit_value < original_exit_value  # higher cap = lower value
```

These tests cost real CI time (headless LibreOffice recalc takes
~30s). Run only in the full CI gate, not the light gate.

### 8.3 Existing tests carry forward

The bidirectional doc-export validator from v2 §7 still runs on every
commit. Every new named range introduced in commit 1 needs a glossary
entry tagged `investor` in [`FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md).

---

## 9. Risks & Open Items

1. **LibreOffice recalc fidelity.** CI uses headless LibreOffice to
   force formula evaluation so `data_only=True` can read cached
   values. LibreOffice's IRR / XIRR / data-table impl is *very close*
   to Excel's but not byte-identical. Tolerance of 0.01 absolute /
   0.01% relative should cover the gap; if it doesn't, switch the
   CI test runner to use a Windows-hosted Excel COM bridge, which is
   significant infra work.

2. **Cell-comment fatigue.** Auto-sized debt modules + draw-schedule
   cells need user-visible warnings ("engine-computed, edit and
   re-export"). Cell comments work but clutter the UI. Open question
   whether to use a `legend` row at the top of the Assumptions sheet
   listing all engine-only fields by name instead.

3. **Excel feature parity.** Some users open the file in Numbers
   (Mac) or Google Sheets. Data Tables, defined-name resolution, and
   `XIRR` all behave subtly differently. Recommend documenting
   "Excel 2016+ on Windows or Mac" as the supported runtime in the
   workbook footer.

4. **Schema drift.** When `CapitalModule.source` / `.carry` schemas
   change, Block C breaks silently. Mitigation: the parity test
   (§8.1) covers every named range; if `s_module_{m}_term_years`
   stops being emitted, parity fails on every fixture. CI catch.

5. **Performance.** A 240-period Debt Schedule with 4 loans and
   amortization formulas + an active two-way Data Table will recalc
   noticeably (~1–2 sec on a mid-spec laptop). Acceptable for an LP
   workflow but might surface UX friction with very long holds.

6. **Existing Phase H3 color convention.** All blue-input cells today
   are intended as "you can edit this." With formula conversion, the
   blue-input set grows ~3×. Verify the legend on the Cover sheet
   reflects the expanded set after commit 1.

---

## 10. References

| Need | Where |
|---|---|
| Prior plan (v2, completed) | [`Completed/investor-excel-export-v2.md`](./Completed/investor-excel-export-v2.md) |
| Current exporter | [`app/exporters/investor_export.py`](../../app/exporters/investor_export.py) |
| Workbook helpers + `CellRegistry` | [`app/exporters/_workbook_helpers.py`](../../app/exporters/_workbook_helpers.py) |
| Doc validator (glossary parser) | [`app/exporters/_doc_validator.py`](../../app/exporters/_doc_validator.py) |
| Math reference | [`docs/FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md) |
| Cashflow engine | [`app/engines/cashflow.py`](../../app/engines/cashflow.py) |
| Interest math (day-count) | [`app/engines/interest.py`](../../app/engines/interest.py) |
| Draw schedule solver | [`app/engines/draw_schedule.py`](../../app/engines/draw_schedule.py) |
| Underwriting rollup | [`app/engines/underwriting_rollup.py`](../../app/engines/underwriting_rollup.py) |
| Waterfall engine | [`app/engines/waterfall.py`](../../app/engines/waterfall.py) |
| Reference investor models | `docs/models/HelloData MultiFamily Model.xlsx`, `docs/models/Original-Apartment-Acquisition-Model-v2.41-3ylxhk.xlsx` |
