# Vicinitideals Financial Model — Math, Assumptions, and Justification

**Purpose.** This document is the source of truth for every formula the cashflow and waterfall engines use. If someone asks "what is this math based on?", the answer lives here. Each section gives:

1. The variable-form formula (as it appears in code)
2. A plain-English translation using CRE conventions
3. Why we chose that formulation over alternatives
4. The specific file/line reference in the codebase

**Scope.** Sources, Uses, Revenue, OpEx, Reserves, Period Cash Flow, Debt Service, Waterfall, Profit Metrics (IRR/MOIC/Cash-on-Cash). The schema is defined in `app/models/*.py`; the math lives in `app/engines/cashflow.py` and `app/engines/waterfall.py`.

**Formula-driven in the Excel export (2026-05-22, plan
[investor-excel-formula-conversion.md](feature-plans/investor-excel-formula-conversion.md)).**
The investor workbook ships these cells as live Excel formulas
referencing the Assumptions / Cash Flow / Pro Forma cells instead of
engine-computed scalars — an LP edit propagates on workbook recalc:

- Sources & Uses: Project Total Uses, Category Subtotals, Total Uses,
  Total Sources, Sources Gap, Implied Equity Required.
- Cover: Total Uses and Total Sources headline values (cross-sheet
  references to S&U totals).
- Underwriting Pro Forma: Effective Gross Income, NOI (sum/diff of
  same-sheet rows).
- Underwriting Cash Flow: Levered Cash Flow, Unlevered Cash Flow,
  DSCR (annual), Cumulative Cash Flow.
- Investor Returns: Return ($) per CapitalModule, Combined Levered
  IRR (scenario) — `=IFERROR(IRR(r_uw_cf_levered),0)`.
- Debt Schedule: Loan Summary Annual P&I for `pi` carry-type rows
  (`PMT(rate/12, amort*12, -principal) * 12`).

Everything else — NOI per year, OpEx, Debt Service, Equity Multiple,
sensitivity grid, waterfall tier accruals — stays engine-computed for
now. The remaining conversion work is enumerated in the plan doc
under "Out of plan-scope but follow-up candidates."

**Conventions used throughout.**
- `TPC` = Total Project Cost (all non-exit, non-balance-only Use lines)
- `P` = principal of a sized loan
- `f_c` = construction interest factor (fraction of principal consumed by construction-period interest)
- `f_m` = monthly P&I payment factor (standard amortization)
- `L` = lease_up_months
- `R` = operation_reserve_months
- `N` = number of months in a loan's active phase (for carry calculations)
- `NOI` = Net Operating Income (annual unless specified)
- `DS` = Debt Service
- `EGI` = Effective Gross Income (gross revenue − vacancy loss)
- `DSCR` = NOI / DS

**Tagged metric headers — audience tagging convention.** Headers throughout this
doc follow one of two shapes:

1. **Tagged metric header.** A `##` or `###` header that ends with a bracketed
   audience list, e.g. `### DSCR [investor, lender, app]`. These are
   machine-parsed by [`app/exporters/_doc_validator.py`](../app/exporters/_doc_validator.py)
   and drive the **Glossary** sheet of the investor Excel export — so any
   metric tagged `investor` automatically surfaces in the workbook the LP
   receives. Body convention: `**Definition.**`, `**Calculation.**` (often a
   code block), `**Engine source.**`, `**Notes / edge cases.**` paragraphs.
2. **Untagged structural header.** A `##` or `###` header without brackets
   (most of the existing section/sub-section headers in this doc, e.g.
   `## 2. Sources / Debt Sizing`). These describe processes or methodology
   and are **not** treated as metrics. The validator skips them.

**Audience tags** (one or more, comma-separated):

- `investor` — appears in the LP-facing Investor Excel export
- `lender` — lender-facing metric (DSCR, LTV, debt yield, balloon, prepay)
- `app` — surfaces in the web UI (status pills, tooltips, KPI cards, modals)
- `internal` — engine implementation detail; never user-facing

Most metrics will be `[investor, lender, app]` (the LP package + the lender
package + the app UI all want it). LP-only metrics drop `lender` (e.g. promote,
catchup); lender-only metrics drop `investor` (e.g. debt yield, balloon).
Process headers (auto-sizing internals, fix-point iteration, refi math)
deliberately carry no tag.

### Multi-project engine (Phase 2, merged 2026-04-21) — math unchanged per project

Migrations `0048` (junction + anchors), `0050` (`project_id` on cashflow output tables), and `0051` (UNIQUE swap) let one Scenario compute N Projects' cashflows independently. The engine loops per project; each project reads its own UseLines, IncomeStreams, OpEx, OperationalInputs, Milestones, and a junction-filtered view of CapitalModules. Output rows (CashFlow, CashFlowLineItem, OperationalOutputs) carry `project_id`. The `app/engines/underwriting_rollup.py` module aggregates across projects for Scenario-level display.

**None of the formulas in this document changed.** Every per-project computation runs the same math as pre-Phase-2: same TPC, same auto-sizing, same carry types, same DSCR convergence, same XIRR, same waterfall. Validated byte-identical against 5 baseline prod scenarios (`tests/phase2_baseline/*.json`).

### Shared Sources — independent sizing, grouped display

A **shared Source** is one `CapitalModule` (one contract identity — one lender, one rate, one carry_type, one exit vehicle) attached to multiple Projects via `capital_module_projects` junction rows. Product decision (2026-04-21): each project sizes its own share against its own numbers. No cross-project constraint pooling.

**Per-project amount read path (Phase 2c1, 2026-04-22):** the engine now reads `junction.amount` per project rather than the scenario-aggregate `module.source.amount`. `_per_project_capital_modules` overlays the junction's amount and `auto_size` flag onto the in-memory module at load time. `_sync_junction_amounts_after_compute` writes the auto-sized amount back to the active project's junction row after auto-sizing completes, so the Coverage modal reflects the computed amount on the next render. Single-project scenarios are byte-identical because the Phase 1 backfill made `junction.amount == module.source.amount`; the overlay early-returns on the match check.

- **Per-project sizing**: Project A's share of Source-1 is sized on A's DSCR / LTV / gap-fill against A's uses. Project B's share is sized on B's. Total principal on the loan = Σ per-project principals.
- **Per-project carry / IR / CI**: each project's `Interest Reserve` / `Capitalized Construction Interest` / `Acquisition Interest` UseLine is sized on that project's own uses × carry factor, where the carry factor's `N` comes from the module's active window (which in turn is bounded by the exit vehicle). Since a shared Source has one exit vehicle, `N` is the same across covering projects.
- **Draw cadence**: at the engine's month-level resolution, joint cadence (one requisition on the 1st) and independent cadence (each project draws on its own schedule) produce identical numbers, because the cadence factor `(N+1)/2` (interest_reserve) or `N` (capitalized_interest) is calendar-month-integer-based. Day-level divergence (Project A draws on day 1, Project B draws on day 15 and pays 2 extra weeks of carry) is not representable at month resolution. Phase 2f joint-cadence code is deferred until day-level modeling lands.
- **Underwriting-level DSCR / LTV on a shared Source**: informational notification only. No feedback into sizing.
- **Rollup display**: `rollup_sources` returns one row per CapitalModule with `total_principal = Σ junction.amount`, `covered_project_ids`, and `is_shared: bool`. The UI draws a "covers: P1, P2" chip on shared rows.

**Per-project DSCR and IRR are computed from each project's own cashflow rows.** The cashflow engine writes per-project `OperationalOutputs.dscr` (NOI ÷ annual DS using junction-overlaid principal) and per-project unlevered IRR during its per-project loop. The waterfall engine's `_apply_levered_metrics` recomputes DSCR + levered IRR for the **default project only** (`outputs.project_id = oldest project`); for non-default projects the cashflow engine's values are authoritative. **The waterfall engine does not overwrite `cash_flow.debt_service`, `net_cash_flow`, or `cumulative_cash_flow` for any deal** (single- or multi-project). The cashflow engine is the sole writer of those columns. `_apply_levered_metrics` reads `net_cash_flow` to build `levered_cashflows` for XIRR, then recomputes DSCR using the cashflow engine's `debt_service` values. This applies uniformly — `WaterfallResult.cash_distributed` for the `debt_service` tier is a residual NCF allocation (what's left after DS is already deducted), not the PMT obligation.

**Synthetic Owner Equity is per-project.** `_ensure_equity_and_tiers` walks every project on the scenario, joins through `capital_module_projects` to find which projects already have an equity module attached, and creates a synthetic `Owner Equity` (common_equity, $0, residual interest) for each project that lacks one — with a junction row tying the synthetic to that specific project. The default for new equity is per-project, not shared; users opt into sharing via the Add Project drawer's share-source checkbox. Single-project scenarios are unchanged: if the lone project has no equity, one is created and attached.

### Underwriting rollup CF display — NOI-focused (Phase 3a)

The Underwriting tab's Combined Cashflow table shows only **NOI / Debt Service / Net CF** — no Revenue, EGI, or OpEx columns. Reason: only these three fields sum meaningfully when projects are in different income modes.

| Field | NOI-mode contribution | Rev/OpEx-mode contribution | Summable across modes? |
|---|---|---|---|
| NOI | stabilized NOI input | revenue − opex | ✅ always |
| Debt Service | ✅ | ✅ | ✅ always |
| Net CF | ✅ | ✅ | ✅ always |
| Revenue / EGI | == NOI (by construction) | revenue − vacancy | ⚠️ inflates combined total for mixed |
| OpEx | $0 (no breakout) | actual opex | ⚠️ under-reports combined total for mixed |

Today `income_mode` is a scenario-level setting (one value per Scenario, applied to every Project). The "mixed mode across projects" case is not yet possible in prod — but the NOI-focused rollup is the right design regardless, because:

- All-NOI scenarios: showing Revenue/OpEx $0 alongside NOI is just noise.
- All-Rev/OpEx scenarios: the detail is still available per-project on the Cashflow module panel; the Underwriting tab is a lender-summary view, not a line-level projection.
- Mixed scenarios (future, when `income_mode` might become per-project): NOI / DS / Net CF are the only columns that stay honest.

The per-project Cashflow module panel shows a purple "Mode: NOI" chip in its header when that scenario is in NOI mode, so operators looking for missing Revenue/OpEx rows see the reason immediately.

### Cross-project compute order

`app/engines/anchor_resolver.py` orders projects via Kahn topological sort over `project_anchors` rows (anchored project runs after its parent). Cycles raise `AnchorCycleError`. Zero-anchor scenarios fall through to `sorted(created_at)` — byte-identical to pre-Phase-2 ordering.

### Anchor-driven date resolution (Phase 2d1, 2026-04-23)

`resolve_project_start_dates(scenario, session) -> dict[project_id, date]` walks the anchor chain in topological order. For each anchored project:

1. Look up the pivot: `anchor_milestone_id` on the parent project (or the parent's earliest milestone by `sequence_order` if `anchor_milestone_id` is null).
2. Compute pivot's end date via the standard `Milestone.computed_end()` resolver.
3. `child.start = pivot.end + offset_months + offset_days`. Month arithmetic clamps to the target month's last day (so Jan 31 + 1 mo = Feb 28/29) before adding `offset_days`.

`compute_cash_flows` calls the resolver before the per-project loop and passes each project's resolved date as `project_start_override` into `_compute_project_cashflow`. The inner function computes `delta = override − min(milestone_dates.values())` and shifts every phase-key date by `delta` — internal phase chain timing is preserved; only the whole project slides. For zero-anchor scenarios the resolver returns `{}`, no override is applied, and math is byte-identical to the pre-2d1 engine.

Cycle detection runs both at read time (`ordered_projects` Kahn pass) and at write time (POST `/ui/models/{id}/anchors`) before the row is committed, so a user can never create a P1→P2→P1 loop.

---

---

## 1. Uses / Total Project Cost (TPC)

### Total Project Cost (TPC) [investor, lender, app]

**Definition.** Sum of every capital outflow required to acquire, build, lease
up, and stabilize a project — every Use line that is not exit-phase and not
a balance-only label.

**Calculation.**
```
TPC = Σ UseLine.amount
        where ul.phase != "exit"
          and ul.label not in _BALANCE_ONLY_LABELS
```

**Engine source.** `compute_cash_flows` (`app/engines/cashflow.py`) computes
TPC during the per-project loop and writes it to
`OperationalOutputs.total_project_cost`. The underwriting rollup
(`app/engines/underwriting_rollup.py`) sums it across projects for scenario
display.

**Excel formula (Phase 4 KPI-tail conversion, 2026-05-25).** The
Underwriting Summary "Total Project Cost" cell is now
`=IFERROR(s_su_uses_total - s_su_balance_only_total, <engine_fallback>)`.
A new "Balance-Only Subtotal" row on the S&U sheet (named range
`s_su_balance_only_total`) sums every Use-line row whose label is in
the engine's `_BALANCE_ONLY_LABELS` set (Operating Reserve, Lease-Up
Reserve, Capitalized Construction Interest, Construction Interest
Reserve, Capitalized Pre-Development Interest, Capitalized Acquisition
Interest, Interest Reserve, Pre-Development Interest Reserve,
Acquisition Interest Reserve, Construction DS Reserve). Subtracting
this from `s_su_uses_total` matches the engine's
`_calculate_total_project_cost`, which excludes the same set from
capital_event outflows. LP edits to any Use-line amount (or to
`s_operating_reserve_months` for the derived Operating Reserve row)
ripple to TPC without re-running the engine.

**Notes / edge cases.** TPC excludes Operating Reserve, Lease-Up Reserve, and
capitalized-interest stubs because those are derived from the principal we
are sizing — including them would double-count loan-funded items as costs the
loan needs to cover. See **Total Uses** for the all-inclusive sum used on the
visible S&U panel and the equity stack. See §1.1 below for the full prose
treatment.

### Total Uses [investor, lender, app]

**Definition.** Sum of every non-exit Use line including reserves and
capitalized-interest stubs. The number that matches the line items the user
sees on the Sources & Uses panel.

**Calculation.**
```
total_uses = Σ UseLine.amount where ul.phase != "exit"
```

**Engine source.** `compute_cash_flows` (`app/engines/cashflow.py`) computes
this and the rollup exposes it as `rollup_summary["total_uses"]`. The
Underwriting KPI strip displays it as the headline "Total Uses" tile (with
TPC as a sub-label).

**Excel formula (Phase 4 tail).** The "Total Uses" cell on Underwriting
Summary is written as `=s_su_uses_total`, the per-row SUM total on the
Sources & Uses sheet. An LP edit to any Use line on S&U ripples through
to this KPI without re-running the engine. The Python value is retained
only as the named range's address; Excel resolves the formula at file
open. Semantic equivalence is exact — both sides compute
`Σ UseLine.amount where phase != "exit"`.

**Notes / edge cases.** Total Uses ≥ TPC. The delta is the sum of balance-only
labels (Operating Reserve, Lease-Up Reserve, capitalized-interest reserves).
The equity stack ultimately has to fund those out of pocket, which is why
`equity_required` and Sources Gap both key off Total Uses, not TPC.

### Total Sources [investor, lender, app]

**Definition.** Sum of all funded capital source commitments — debt principal (junction-scoped amounts) plus committed equity. The counter-side of Total Uses in the Sources & Uses panel.

**Calculation.**
```
total_sources = Σ CapitalModule junction-scoped amounts (or module.source.amount when no junctions)
               + implied_equity (Uses − explicit Sources, when > $1)
```

**Engine source.** `_compute_sources_gap` in `app/exporters/investor_export.py`.

### Equity Required [investor, app]

**Definition.** Per-project target equity check at close — what the equity
stack has to bring after debt is sized. Writes to
`OperationalOutputs.equity_required`.

**Calculation.**
```
equity_required = max(0, total_uses_per_project − Σ debt_module_principal_via_junction)
```

**Engine source.** `compute_cash_flows` writes per-project values via the
junction-overlay path. The waterfall engine's in-place rewrite of
`equity_required` is **skipped for multi-project scenarios** so the per-project
numbers stay honest. See §1.0 for the full reconciliation.

**Excel formula (Phase 4 KPI-tail conversion, 2026-05-24).** The
Underwriting Summary "Equity Required" cell is now
`=IFERROR(MAX(0, s_su_uses_total - s_su_debt_sources_total), <engine_fallback>)`.
Both operands resolve to S&U named cells whose own formulas chain back
to Assumptions Block C debt principals (`s_<slug>_principal`) and the
per-project Use lines. LP edits to either side ripple to the hero KPI
without re-running the engine. A new "Debt Sources Subtotal" row on
the S&U sheet (named range `s_su_debt_sources_total`) sums only the
debt source rows — excluding the implied-equity gap row — so the
denominator matches the engine's definition.

**Notes / edge cases.** Does *not* subtract committed equity in the Owner
Equity / Preferred Equity modules — that role belongs to **Sources Gap**.
Equity Required is the *raise target*; Sources Gap is the *remaining shortfall*.

### Sources Gap [investor, app]

**Definition.** Scenario-wide remaining funding shortfall after both debt
sizing and the user's committed equity entries. Shrinks toward zero as the
user fills in equity modules.

**Calculation.**
```
sources_gap = Σ total_uses_across_projects
            − Σ junction_scoped_sources (debt + committed equity)
```

**Engine source.** Computed by the Underwriting KPI strip
(`app/templates/partials/underwriting/view.html`) from rollup totals.

**Notes / edge cases.** When committed equity = 0, Sources Gap == Σ Equity
Required. The two diverge once the user starts entering equity commitments.

### 1.0 Two Uses totals — TPC vs. Total Uses

The engine carries two distinct "uses" totals because they answer different questions.

| Number | What it sums | Used for | Excludes |
|---|---|---|---|
| **TPC** (`total_project_cost`) | UseLines that aren't exit-phase **and** aren't `_BALANCE_ONLY_LABELS` | Auto-sizing math, cap rate on cost, debt yield | Operating Reserve, Lease-Up Reserve, Capitalized Construction Interest, Interest Reserve labels |
| **Total Uses** | UseLines that aren't exit-phase | Sources/Uses panel display, **`equity_required`**, Sources Gap | exit-phase only |

The reserves and capitalized-interest stubs are excluded from TPC so the gap-fill solve doesn't double-count loan-funded items as costs the loan needs to cover. They are *included* in Total Uses because the user expects the panel total to match the visible line items, and the equity stack ultimately has to fund Operating Reserve / Lease-Up Reserve out of pocket.

**`equity_required` (per-project, written by `compute_cash_flows`)** = `max(0, Total Uses − Σ debt module principal via junction)`. This is the *target equity check* for the project: what the equity stack has to bring at close after debt is sized. It does not subtract committed equity in the Owner Equity / Preferred Equity modules — that's the role of **Sources Gap**.

**`Sources Gap` (Underwriting KPI strip)** = `Σ Total Uses across projects − Σ junction-scoped Sources (debt + committed equity)`. This shrinks toward zero as the user enters equity commitments into the Owner Equity modules. When committed equity = 0, Sources Gap == Σ Equity Required.

The two numbers reconcile when no equity is yet committed; they diverge once the user starts filling in the equity stack. Equity Required is the *raise target*; Sources Gap is the *remaining shortfall*.

### 1.1 What TPC is

TPC is the sum of every capital outflow required to acquire, build, lease up, and stabilize the project. It is **not** the sum of "hard costs" in the CRE sense — it includes every cost line except sale proceeds and derived/balance-only entries.

**Code (cashflow.py, `total_uses` computation around line 691):**
```python
total_uses = ZERO
for ul in use_lines:
    phase_str = str(getattr(ul.phase, "value", ul.phase))
    if phase_str == "exit":
        continue
    if getattr(ul, "label", "") in _BALANCE_ONLY_LABELS:
        continue
    total_uses += _to_decimal(ul.amount)
```

**Plain English.** Sum every Use line across every phase of the deal, **except**:
- Anything in the `exit` phase (those are sale-related costs subtracted from proceeds, not uses)
- Anything whose label is "balance-only" (see 1.2)

### 1.2 Balance-only Use line exclusions

These labels are excluded from the TPC sum because they are derived from debt sizing itself — including them would double-count the same dollars:

```python
_BALANCE_ONLY_LABELS = {
    "Operating Reserve",
    "Capitalized Construction Interest",
    "Construction Interest Reserve",          # legacy label (pre-rename)
    "Capitalized Pre-Development Interest",
    "Capitalized Acquisition Interest",
    "Interest Reserve",                       # construction IR (new)
    "Pre-Development Interest Reserve",
    "Acquisition Interest Reserve",
    "Lease-Up Reserve",
}
```

**Why.** These are all solved algebraically after debt sizing:
- **Operating Reserve**: `max(OpEx_monthly, DS_monthly) × reserve_months` — depends on the principal we are trying to compute.
- **Interest Reserve / Capitalized Interest**: depends on the principal via `IR = P × rate × months_factor`.
- **Lease-Up Reserve**: depends on perm principal via `(P × pmt_factor × L) − income_offset`.

If these were added to TPC before sizing, we would be asking the lender to cover its own interest bucket with its own principal — a circular double-count.

### 1.3 Phase-based Use line sums (for bridge loan sizing)

In Phase B multi-debt deals, each bridge loan is sized to the costs in its phase:

```python
def _phase_cost_sum(phase_set: set) -> Decimal:
    return sum(
        (_to_decimal(ul.amount)
         for ul in use_lines
         if str(getattr(ul.phase, "value", ul.phase) or "") in phase_set
         and getattr(ul, "label", "") not in _BALANCE_ONLY_LABELS
         and getattr(ul, "label", "") not in _cc_labels),
        ZERO,
    )

pre_dev_costs  = _phase_cost_sum({"pre_construction"})
acq_costs      = _phase_cost_sum({"acquisition", "other"})
constr_costs   = _phase_cost_sum({"construction", "renovation", "conversion"})
```

**Plain English.** The pre-development loan covers costs in the `pre_construction` phase; the acquisition loan covers `acquisition` phase costs (entitlement fees, diligence, purchase price for some deals); the construction loan covers hard-construction costs during `construction` / `renovation` / `conversion` phases.

**Why the `_cc_labels` exclusion?** Closing costs (origination fees, legal, title, appraisal, Phase I ESA) auto-fire at the loan's `active_phase_start`. If we sized the construction loan to include its own origination fee, the fee would grow the loan, which would grow the fee, which would grow the loan — a circular reference. Instead, closing costs are financed by the permanent debt gap-fill, never by the bridge loan being closed. See §2.5.

### 1.4 Auto Developer Fee (Use line, computed)

Every new deal seeds a `UseLine` flagged `is_auto_dev_fee=True`. The `amount` is recomputed every engine pass by `app/engines/dev_fee.py::recompute_auto_dev_fee` from a per-deal-type % times a basis. Users edit the % in the Use drawer; the $ field is read-only.

**Per-deal-type defaults** (org-overridable, then user-overridable when org allows — see [docs/DATA_MODEL.md] for the resolver chain):

| Deal type | Default % | Basis | Phase | Timing |
|---|---|---|---|---|
| acquisition | 5.0 | `purchase_price` | acquisition | first_day |
| value_add | 12.0 | `tpc_excl_self` | construction | spread |
| conversion | 12.0 | `tpc_excl_self` | construction | spread |
| new_construction | 12.0 | `tpc_excl_self` | construction | spread |

**Basis math**:

- `purchase_price` → `pct × OperationalInputs.purchase_price` (falls back to summing acquisition-phase Use lines if `inputs.purchase_price` is null/zero)
- `tpc_excl_self` → `pct × Σ(other UseLine.amount, excluding the auto Dev Fee row itself)`

**Compute order**: dev-fee recompute runs *immediately before* `_auto_size_debt_modules`, so debt sizing reads the updated Uses total. Without this ordering, a value-add or new-construction deal would size its loans against a stale Uses total that excluded the dev fee.

**Disabling for one deal**: set `dev_fee_pct` to 0 in the Use drawer. The auto Dev Fee Use line cannot be hard-deleted (delete endpoints return 403); zero-pct is the contract. Per-deal-type defaults at the org/user level can also be set to 0 to disable for all new deals of a type.

---

## 2. Sources / Debt Sizing

### 2.1 Two paths: Legacy and Phase B (multi-debt)

**Legacy** (kept for deals predating the multi-debt rewrite):
- `OperationalInputs.debt_structure` ∈ {`perm_only`, `construction_and_perm`, `construction_to_perm`}
- Single construction + permanent loan pair
- Untouched by any Phase B logic

**Phase B multi-debt** (all new deals):
- `OperationalInputs.debt_types`: ordered list like `["pre_development_loan", "acquisition_loan", "construction_loan", "permanent_debt"]`
- Bridge loans sized independently to phase costs, then removed from the gap-fill pool
- Permanent debt gap-fills to TPC

The Phase B path is gated by `if debt_types_list:` in `_auto_size_debt_modules()`.

### 2.2 Carry types (pre-operation interest treatment)

There are **four** economically distinct ways a loan can handle interest before operations begin. Each produces a different principal for the same base cost, and each shows up differently on the S&U.

| Carry type | Periodic DS? | Balance at takeout | Default sizing factor |
|---|---|---|---|
| `io_only` (True IO) | Yes — cash paid monthly | Flat (= base cost) | `f_io = 0` |
| `interest_reserve` | No — pre-funded pool | Base cost only | `f_io = rate/12 × (N+1)/2` |
| `capitalized_interest` | No — PIK accrual | Base + accrued interest | `f_io = (1+rate/1200)^N − 1` |
| `pi` | Yes — amortized | Decreasing | N/A (standard amort) |

**Why four, not three?** Industry references (Argus, REFM, FDIC handbook) consistently separate True IO from Interest Reserve. Our engine formerly conflated them; Phase 1 of the carry-type rewrite (April 2026) split them to match practice.

**The average-draw factor for Interest Reserve.** Industry convention often cites "50% of the commitment" as the IR factor. That is the large-N limit of a precise formula we can compute exactly because we model monthly draws:

> For `N` evenly spaced monthly draws, the average outstanding balance over the construction period is `(N+1)/(2N)` of the full commitment. Multiplied by the monthly rate, the interest-consumption fraction is `rate/12 × (N+1)/2`.

For `N = 12`, that is `rate/12 × 6.5 = 0.5417 × rate`. Compared to the naive 50% heuristic, the exact factor is 8% larger — material on short construction timelines.

**Day-precise interest (Phase H, May 2026).** The statistical `(N+1)/2` and `N` factors above are used for the sizing solve (principal calculation). Monthly cashflow line items use `period_interest_months()` from `app/engines/interest.py`, which applies actual day-count conventions (`actual_360` default) for precise period-by-period interest accrual. The sizing factors remain the same algebraically; only the period-level cash flows gain day-count precision.

**The full-balance factor for Capitalized Interest.** Capitalized interest (PIK) accrues on the full commitment from day one — there is no "average draw", because the lender imputes full balance. The factor is `(1+rate/1200)^N − 1` (compound monthly accrual; June 2026). Prior versions used `rate/12 × N` (simple interest), which underestimates carry by ~3–4% on 12-month windows and more on longer windows. `draw_type` does not affect CI sizing — compound full-balance accrual applies unconditionally.

**Override: `source.draw_type` decouples carry type from draw schedule (May 2026).** The defaults above assume the conventional pairing — Interest Reserve goes with construction-style monthly draws (`(N+1)/2`); Capitalized Interest goes with a fully-drawn balance (`N`). Real products break this pairing: a tax-exempt bond carrying an Interest Reserve is *fully drawn* into escrow at close, so interest accrues on the full balance even though the carry type is IR.

The optional `CapitalModule.source.draw_type` field overrides the default factor:

| `draw_type` | Effect on `f_io` | Typical product |
|---|---|---|
| `"fully_drawn"` | `rate/12 × N` (full balance for whole period) | Bond, term note, perm loan with proceeds in escrow |
| `"draw_down"` | `rate/12 × (N+1)/2` (average balance over linear draws) | Construction loan, mini-perm |
| `null` (default) | Carry-type convention: IR → draw_down, CI → fully_drawn | Backward-compatible default |

Both the principal solve and the Interest Reserve Use line writer (`app/engines/cashflow.py`, perm path around line 3130) read `draw_type` and apply the same factor — required for `Sources = Uses`. The mapping helper `_draw_schedule_for(carry_type, draw_type)` returns the `"lump"` (fully_drawn) or `"linear"` (draw_down) argument passed to `period_interest_months()`.

For perm-only structures (no separate construction loan in the stack), the perm path substitutes `fully_drawn` when `draw_type` is null rather than the IR carry-type convention — perm proceeds are fully drawn at close in practice. Legacy modules without `draw_type` set continue to behave as before.

**Code (cashflow.py, construction loan branch around line 958):**
```python
elif _ft == "construction_loan":
    _r = Decimal(str(_cr or 0))
    _cl_ct = _carry_type_for_phase(_carry, is_construction=True)
    _n = _loan_pre_op_months(_m)   # per-loan active-window months (see §2.8)
    if _cl_ct == "interest_reserve":
        _io_f = (_r / HUNDRED / Decimal("12")
                 * (Decimal(_n + 1) / Decimal("2"))
                 ) if (_r > ZERO and _n > 0) else ZERO
    elif _cl_ct == "capitalized_interest":
        # compound: _io_f = factor-1 → _div = 2-factor → principal = funded/(2-factor)
        _io_f = (ONE + _r / Decimal("1200")) ** _n - ONE
    else:  # io_only
        _io_f = ZERO
    _div = ONE - _io_f
    _principal = _q(constr_costs / _div) if (_div > ZERO and constr_costs > ZERO) else constr_costs
```

> **April 2026 change:** `constr_months_total` was replaced by `_loan_pre_op_months(_m)` which computes month count within each loan's `[active_phase_start, active_phase_end)` window. See §2.8 for details.

**Derivation of the principal solve.** For IR/IO where `interest = P × f_io` (linear in P):
> `P = base_costs + P × f_io` → `P = base_costs / (1 − f_io)`

For CI where `interest = P × (F−1)` with `F = (1+r/1200)^N` (also linear in P):
> `P = base_costs + P × (F−1)` → `P × (2−F) = base_costs` → `P = base_costs / (2−F)`

In both cases `_div = 1 − f_io` so the same `_principal = funded / _div` line produces the right answer when `f_io` is set correctly for each carry type. CI sets `f_io = F−1` so that `_div = 2−F`.

This is self-consistent: the interest amount `P − base_costs = P × f_io / (1 − f_io) × (1 − f_io) / 1 = base × f_io / (1 − f_io)`.

### 2.3 Bridge loan sizing (per funder type)

#### Pre-development loan
**Formula.** `P_predev = pre_dev_costs / (1 − f_io)` where `f_io` uses pre_dev_months and pre_dev_rate.

**Plain English.** Size the pre-dev loan to cover pre-construction costs (entitlements, design, diligence) plus whatever pre-opening interest its carry type produces.

#### Acquisition loan
**Formula.** `P_acq = acq_costs × LTV / 100`

**Plain English.** Size to a loan-to-value percent of acquisition-phase costs. Default LTV = 70% unless overridden via `CapitalModule.source.ltv_pct` on the acquisition-loan module.

**Why LTV and not gap-fill?** Acquisition loans are sized on the appraised value of what is being acquired, not on the residual capital stack. LTV is the standard industry input.

#### Construction loan
**Formula.** `P_constr = constr_costs / (1 − f_io)` — same shape as pre-dev, with construction months and construction rate.

#### Bridge (generic)
No auto-sizing; whatever amount is on the module is used as-is. Bridge loans are often sized deal-by-deal on collateral value, so we leave it to the user.

**Why are bridges "removed" from the gap-fill pool?** After sizing, each bridge module is excluded from `auto_modules` (`auto_modules = [x for x in auto_modules if x is not _m]`). Only the permanent debt (or equity) gap-fills the remaining hole. Without this, the perm would shrink by whatever the bridge covered, breaking the Sources = Uses invariant.

### 2.4 Permanent debt — gap-fill solve

This is the core debt sizing formula. It is a closed-form solve for the principal that lands cash-at-stabilization exactly on the operating reserve target.

#### Derivation

Let:
- `P` = perm principal (what we're solving for)
- `TPC` = total uses (after bridge interest costs + perm flat closing costs have been added)
- `fixed` = fixed (non-auto-sized) sources (equity, grants, etc.)
- `I_lu` = lease-up income offset (see §2.6 below)
- `f_c` = constr_io_factor — 0 in Phase B multi-debt (the construction loan handles its own IO); nonzero only in the legacy single-loan path
- `f_m` = pmt_factor = `i·(1+i)^n / ((1+i)^n − 1)`, where `i = rate/12/100`, `n = amort_years × 12`
- `L` = lease_up_months
- `R` = operation_reserve_months

The gap-fill invariant is: **perm principal + fixed sources = TPC + construction IO + lease-up DS shortfall + operating reserve**.

Writing each term as a fraction of `P`:
> `P + fixed = TPC + P·f_c + (P·f_m·L − I_lu·L) + P·f_m·R`
> `P − P·f_c − P·f_m·(L + R) = TPC − fixed − I_lu·L`
> `P·(1 − f_c − f_m·(L + R)) = TPC − fixed − I_lu·L`
> `P = (TPC − fixed − I_lu·L) / (1 − f_c − f_m·(L + R))`

#### Code (cashflow.py, gap-fill solve in `_auto_size_debt_modules`)
```python
divisor = ONE - constr_io_factor
_m_cc = _cc_data.get(id(module))
if _m_cc and _m_cc["pct"] > ZERO:
    divisor -= _m_cc["pct"]                 # perm closing-cost % (see §2.5)

# effective_uses = TPC − fixed − lease_up_income_offset
effective_uses = total_uses - fixed - lease_up_income_offset

ds_divisor = divisor - pmt_factor * Decimal(reserve_months + lease_up_months)
if ds_divisor > ZERO:
    principal = _q(effective_uses / ds_divisor)
```

**Plain English.** Solve for the perm loan amount that:
1. Covers every non-exit Use line
2. Covers the construction IO carry (if the loan is bearing it — legacy only)
3. Covers its own closing-cost origination fee (via the divisor adjustment)
4. Covers the debt-service shortfall during lease-up (net of the 1/3 phantom NOI — see §2.6)
5. Leaves exactly `reserve_months × DS` in the bank at first stabilized month

If any of those terms is zero (no construction phase, no lease-up, etc.) the formula collapses gracefully — that term drops out.

**What if `ds_divisor ≤ 0`?** That means the principal requirement, reserves, and lease-up carry exceed the amortization budget — i.e., the deal can't support the requested reserve structure. The engine falls back to an opex-based reserve without lease-up adjustment (cashflow.py:1126).

#### Rate + amort precedence — must match what cashflow pays

The sizer's `rate_pct` and `amort_years` are resolved by `_op_phase_rate_and_amort(carry, src)` (cashflow.py) with this precedence:

1. **`carry.schedule[]` first IO/PI phase** — the same value `_period_ds_from_schedule_phase` uses to charge operating debt service month-over-month. Authoritative for any loan using the modern schedule format.
2. **`carry.phases[name='operation']`** — legacy phased-carry format (deprecated, still supported).
3. **`source.interest_rate_pct` / `source.amort_term_years`** — flat / legacy fallback.
4. **`carry.io_rate_pct` / 30y** — final fallbacks for the oldest deal records.

**Why it matters.** The sizer solves for the principal that hits the DSCR / gap-fill target *at a specific rate*. Cashflow then pays debt service at whatever rate the schedule says. If the two disagree, sized DSCR ≠ realised DSCR and the Operating Reserve UseLine writes a value different from what the sizer assumed, leaving a residual Sources gap.

The Operating Reserve write-back at `actual_reserve = max(opex_monthly, ds_monthly) × reserve_months` uses the same helper so the sized-vs-paid invariant holds end-to-end.

**Concrete example of the bug class (fixed May 2026).** Deal with `source.interest_rate_pct = 6.0` and `carry.schedule[PI].rate_pct = 5.5`, DSCR floor 1.15, dual-constraint mode. Pre-fix: sizer hit DSCR 1.15 at 6.0%, cashflow paid at 5.5% (~5.6% smaller payment), realised DSCR landed at `1.15 × pmt(6%)/pmt(5.5%) ≈ 1.214`. Post-fix: sizer uses 5.5% directly, realised DSCR ≈ 1.15.

### 2.5 Closing costs (Phase B only)

#### Defaults

Market-backed, April 2026 (sources: commloan.com, financelobby.com, aegisenvironmentalinc.com, mrrate.com):

```python
_DEFAULT_LOAN_COSTS = {
    "construction_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
        {"label": "Environmental Phase I", "flat": Decimal("2500")},
    ],
    "permanent_debt": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("0.5")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Appraisal",             "flat": Decimal("3500")},
        {"label": "Title",                 "flat": Decimal("2500")},
    ],
    "pre_development_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "acquisition_loan": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.0")},
        {"label": "Lender Legal",          "flat": Decimal("5000")},
        {"label": "Title / Survey",        "flat": Decimal("3500")},
    ],
    "bridge": [
        {"label": "Origination Fee",       "pct_of_principal": Decimal("1.5")},
        {"label": "Lender Legal",          "flat": Decimal("3000")},
    ],
    "bond": [
        {"label": "Bond Issuance Fee",     "pct_of_principal": Decimal("1.0")},
        {"label": "Bond Counsel Legal",    "flat": Decimal("15000")},
    ],
}
```

**Why these specific numbers?**

| Cost | Range in market | Our default | Source |
|---|---|---|---|
| Construction orig | 0.5–2% (banks 0.5–1%, private 1–2%) | 1.0% | commloan, mrrate |
| Perm orig (agency/bank) | 0.25–1.0% | 0.5% | financelobby |
| Pre-dev / bridge orig | 1.5–3% | 1.5% (low end) | hurstlending, thecreditpeople |
| Lender legal | $3k–$15k (CMBS higher) | $5k (construction/perm); $3k (pre-dev/bridge) | rochfordlawyers, financelobby |
| ALTA survey + title | $2.5k–$10k combined | $3.5k | fastercapital |
| Appraisal (commercial) | $3k–$5k+ | $3.5k | loanbase |
| Phase I ESA | $2k–$5k | $2.5k (median) | aegisenvironmental, geoforward |
| Bond counsel | $10k–$25k | $15k | specialized muni convention |

These are **starting points**. Users can override any cost line in the S&U table and the engine will respect the override.

#### How flat vs. % costs are handled differently

**Flat costs** are known before sizing — they get added to `total_uses` directly:

```python
# (cashflow.py around line 995)
for _cc_obj in _cc_data.values():
    _cc_ref = _cc_obj["module"]
    if id(_cc_ref) in _auto_mod_ids:
        total_uses += _cc_obj["flat"]    # perm flat: add to TPC before gap-fill
    else:
        _cc_br_p = Decimal(str((_cc_ref.source or {}).get("amount") or 0))
        total_uses += _cc_obj["flat"]
        total_uses += _q(_cc_br_p * _cc_obj["pct"])   # bridge: principal known, add now
```

**Percent-of-principal costs** for the perm loan are the tricky case. The origination fee is `P × 0.5%`, but `P` is what we're solving for. We fold the % into the divisor:

> **Naive (wrong):** `P = TPC / divisor`, then origination fee = `P × 0.5%`. But then TPC should have grown by that fee, and P should have grown to cover it. Iterative, never converges in one pass.
>
> **Algebraic (correct):** `P × (1 − 0.5%) = TPC`, so `P = TPC / 0.995`. One pass, exact.

That is what the line `divisor -= _m_cc["pct"]` does — it extends the gap-fill divisor by the perm origination percent. The result is that on the first compute run, `Sources = Uses` holds exactly, not approximately.

**Verified April 2026**: all three Phase B regression tests pass with `Gap = $0` on first compute.

#### The `_cc_labels` exclusion from `_phase_cost_sum`

Closing cost Use lines live at `active_phase_start` of their loan. A construction loan's origination fee lives in `pre_construction`, because that's when the loan closes. But `pre_construction` is also the phase that sizes the pre-dev loan. Without an exclusion, the pre-dev loan would grow to cover the construction loan's origination fee — wrong.

We pre-compute the full set of closing-cost labels before calling `_phase_cost_sum`:

```python
_cc_labels: set[str] = set()
for _pre_cm in capital_modules:
    _pre_ft = str(getattr(_pre_cm, "funder_type", "") or "").replace("FunderType.", "")
    if _pre_ft not in _DEFAULT_LOAN_COSTS or not (_pre_cm.source or {}).get("auto_size"):
        continue
    _pre_cm_lbl = getattr(_pre_cm, "label", "") or _pre_ft.replace("_", " ").title()
    for _pre_cost in _DEFAULT_LOAN_COSTS[_pre_ft]:
        _cc_labels.add(f"{_pre_cm_lbl} — {_pre_cost['label']}")
```

`_phase_cost_sum` skips anything in this set. Closing costs are still in TPC (through the `_cc_data` additions after bridge sizing), so the permanent loan still covers them. They simply don't inflate the bridge loans.

#### User override sentinel

- `amount == 0` (or the Use line doesn't exist) → engine computes from the default table and writes the line
- `amount > 0` → user override — engine leaves it alone and counts it through normal `total_uses`

Users can adjust any closing cost in the S&U table directly. If their actual deal has a 2% origination fee on a construction loan, they change the dollar amount and the engine respects it on the next compute.

### 2.6 The lease-up income offset — why `1/3`, not `1/2`

During lease-up, the perm loan is accruing debt service but income is ramping. The gap-fill formula must decide how much lease-up income to credit against the debt burden. Naive linear accounting would use 50% (half of stabilized, since occupancy ramps 0→100% linearly). That is wrong.

**Why 50% overstates lease-up income.** Operating costs don't scale linearly with occupancy — fixed costs (salaries, insurance, property tax) persist from day one. Variable costs (utilities, maintenance) do scale. A reasonable model is opex ramping from 50% → 100% over lease-up, while revenue ramps 0% → 100%.

**Derivation, assuming 60/40 revenue/opex split at stabilization:**

Let `R` = stabilized revenue, `E` = stabilized opex, `NOI_stab = R − E`. Assume `R = 0.6 × gross`, `E = 0.4 × gross`. Revenue ramps linearly `0 → R`, opex ramps linearly `0.5E → E`.

> Avg revenue over lease-up = 0.5 × R
> Avg opex over lease-up = 0.75 × E
> Avg NOI during lease-up = 0.5R − 0.75E
> Avg NOI as a fraction of stabilized NOI = (0.5R − 0.75E) / (R − E)

With `R = 833k, E = 333k, NOI_stab = 500k`:
> (0.5 × 833 − 0.75 × 333) / 500 = (417 − 250) / 500 = 167 / 500 = **1/3**

**Month-by-month check** (`L = 9`):

| Month | Rev% | OpEx% | Revenue | OpEx | NOI |
|---|---|---|---|---|---|
| 1 | 0% | 50% | $0 | $13,889 | −$13,889 |
| 2 | 13% | 56% | $8,681 | $15,625 | −$6,944 |
| 3 | 25% | 63% | $17,361 | $17,361 | $0 |
| 4 | 38% | 69% | $26,042 | $19,097 | $6,944 |
| 5 | 50% | 75% | $34,722 | $20,833 | $13,889 |
| 6 | 63% | 81% | $43,403 | $22,569 | $20,833 |
| 7 | 75% | 88% | $52,083 | $24,306 | $27,778 |
| 8 | 88% | 94% | $60,764 | $26,042 | $34,722 |
| 9 | 100% | 100% | $69,444 | $27,778 | $41,667 |

Total NOI over 9 months = $125,000. Monthly avg = $13,889 = **33.3%** of stabilized $41,667. ✓

**Impact.** Using 50% instead of 33.3% would overstate lease-up income by 17 percentage points × 9 months × $41,667/month ≈ $63k. That is cash the deal would not actually generate. By the time the model told you so, you'd be 9 months into lease-up with a shortfall.

**Code (`_LEASE_UP_INCOME_FACTOR` constant):**
```python
_LEASE_UP_INCOME_FACTOR = Decimal("1") / Decimal("3")
noi_monthly_est = noi_annual / Decimal("12") if noi_annual > ZERO else ZERO
lease_up_income_offset = _q(noi_monthly_est * _LEASE_UP_INCOME_FACTOR * Decimal(lease_up_months))
```

### 2.7 DSCR-capped mode

Some deals use a different sizing mode: size the loan to the **minimum DSCR** required by the lender, not to the gap. This is selected via `OperationalInputs.debt_sizing_mode = "dscr_capped"`.

**Logic:**
1. Compute the gap-fill principal `P_gap` using §2.4.
2. Compute the resulting DSCR at stabilization: `DSCR_gap = NOI / (P_gap × pmt_factor × 12)`.
3. If `DSCR_gap ≥ module.source.dscr_min` (fallback `1.25`): use `P_gap` (the lender's minimum doesn't bind).
4. Otherwise: cap the principal so DSCR exactly equals the minimum. This is solved iteratively by `newton_solve.solve_principal_for_dscr()` (Newton-Raphson with bisection fallback) because amortizing loans produce a non-linear relationship between principal and debt service:
   > `DS_target = NOI / DSCR_min / 12`
   > `P_capped` = Newton-Raphson root of `DS(P) − DS_target = 0`

   The closed-form `P_capped = DS_target × PV_annuity_factor` (where `PV_annuity_factor = (1 − (1+i)^(-n)) / i`) is the starting guess and exact solution for standard amortizing loans; Newton-Raphson generalises this for IO-period and day-count variations.

This shows the user a **real funding gap** in the S&U table (Uses > Sources) rather than silently levering up past what the lender would actually fund.

### 2.8 Dual-constraint mode (MIN of LTV, DSCR, gap-fill)

Industry-standard loan sizing: the lender computes both LTV-based and DSCR-based maximums and funds the smaller. Selected via `debt_sizing_mode = "dual_constraint"`.

**Where each input lives (post 2026-04-29 refactor, alembic 0060).** `debt_sizing_mode` lives on `OperationalInputs` (deal-level). **DSCR floor** is per-loan: `CapitalModule.source.dscr_min` for permanent-debt modules. Engine reads inside the per-module sizing loop; falls back to `PLACEHOLDER_DSCR = 1.25` if unset. **LTV** is also per-loan: `CapitalModule.source.ltv_pct`. There is no `OperationalInputs.dscr_minimum` and no `inputs.ltv_maximum_pct` column — any code reading those names is a bug or pre-refactor stale. The wizard's `inputs.debt_terms.{funder_type}.{ltv_pct,dscr_min,hold_term_years,rate_pct,amort_years}` JSON is **wizard staging only**; engine reads `CapitalModule.source` directly. Default LTV when absent is funder-type-specific (typically 70% for acquisition, 75% for perm).

**Logic:**
1. Compute the gap-fill principal `P_gap` using §2.4 (with closing-cost divisor fold-in).
2. Compute LTV-based principal:
   > `property_value = NOI_annual / cap_rate`
   > `P_ltv = property_value × LTV%`

   The cap rate defaults to the going-in cap (`exit_cap_rate_pct`) but can be overridden via `source.refi_cap_rate_pct` on the CapitalModule.
3. Compute DSCR-based principal:
   > `DS_target = NOI_annual / DSCR_min / 12`
   > `P_dscr = DS_target × PV_annuity_factor`
4. Final principal: `P = MIN(P_gap, P_ltv, P_dscr)`
5. The `binding_constraint` is tagged on the source (`"ltv"`, `"dscr"`, or `"gap_fill"`) for UI transparency.

**Why three-way MIN?** `P_gap` acts as a ceiling: no point funding more than the project actually needs. `P_ltv` and `P_dscr` are lender constraints. The binding one determines what the lender will actually write.

### 2.9 Balloon balance tracking

Remaining loan balance at any point in time, handling IO-then-amortizing transitions:

```
if months_elapsed <= io_months:
    balance = principal                         # still in IO period
else:
    n_amort = months_elapsed − io_months
    factor = (1 + r)^n_amort
    balance = principal × factor − pmt × (factor − 1) / r
```

Where `pmt = _monthly_pmt(principal, rate, amort_years)` and `r = rate / 12`.

Used by: refi proceeds calculation (§2.10), prepay penalty at exit (§6.4).

### 2.10 Cash-out refinance (bridge → perm takeout)

**Exit Vehicle is the only input that defines when a loan ends.**

Each Capital Module's `exit_terms.vehicle` declares how its balance is resolved.  The previously user-editable `active_phase_end` field is deprecated — the engine derives the active-end rank from the vehicle at compute time via `_resolve_active_end_rank(module, all_modules)` (in [app/engines/cashflow.py](app/engines/cashflow.py)), with a matching helper `_resolve_waterfall_end_index` in [app/engines/waterfall.py](app/engines/waterfall.py).  The DB column still exists (transition-period rollback safety) but the POST handler writes a derived value on save.

| Vehicle value | Meaning | Refi event? | Derived end-rank |
|---|---|---|---|
| `"maturity"` | Balloon paid at amort term end | No | 99 (perpetuity through exit) |
| `"sale"` | Balloon paid from divestment proceeds | No (handled in exit period) | 6 (exit / divestment) |
| `<module_uuid>` | Another Capital Module absorbs the balance at the handoff point | **Yes** — §2.10 math below | Retirer's `active_phase_start` rank |

**Funder-type classification.** Exit Vehicle applies only to funder types that have a real ending (loans with maturity/refi/sale semantics):

`_EXIT_VEHICLE_APPLIES` = `{permanent_debt, senior_debt, mezzanine_debt, bridge, construction_loan, acquisition_loan, pre_development_loan, soft_loan, bond, owner_loan}`.

All other funder types (preferred_equity, common_equity, owner_investment, grant, tax_credit, other) are perpetuity-like — the waterfall distributes them at exit. **These sources are excluded from the draw schedule engine** (`_run_draw_schedule` filters to debt modules only); equity and grant capital is the cashflow engine's residual, not a sequential draw-schedule layer.  `owner_loan` is promoted to full debt treatment (accrues interest, gets a debt-service line, uses Exit Vehicle).  The UI hides Exit Vehicle + draw cadence for non-exit-vehicle types.

The engine computes pairings in a generic pre-pass. For every module `B`, `_resolve_vehicle(B, all_modules)` reads `B.exit_terms.vehicle` and returns the literal or the retiring module.

**Explicit user picks are honoured regardless of overlap.** If `B.exit_terms.vehicle` is set to another module's UUID and that module exists, the engine uses it — even when the retirer's active window doesn't literally overlap `B.end_rank`. Adjacent-vs-overlapping distinctions are brittle (a new loan often closes the same day the old one matures), so the engine trusts the user's pick and lets the §2.10 refi math handle the handoff.

Default selection (when `vehicle` is unset or points at a missing module):

1. Among eligible retirers (modules whose active window `[start_rank, end_rank)` covers `B.end_rank`), prefer those where `R.start_rank == B.end_rank` (enter exactly at handoff). Tie-break by lowest `stack_position`, then alphabetical label.
2. Else if `B.end_rank >= 6` (exit/divestment): `"sale"`.
3. Else: `"maturity"`.

For each `(B, R)` pair the engine tags `B.source.is_bridge = True`, removes `B` from the gap-fill pool (so only the retirer sizes to TPC), and writes `R.source.construction_retirement = B.amount`. This generalises the legacy `debt_structure == "construction_and_perm"` specialisation — that path now flows through the generic detector and produces identical results.

**Refi cash flow.** When a perm loan has `construction_retirement` set on its source, the engine computes net refi proceeds at the first period of the perm's `active_phase_start`:

```
net_refi = perm_amount
         − bridge_balloon_balance
         − prepay_penalty
         − perm_financing_costs
```

**Components:**
- `bridge_balloon_balance`: computed via §2.9 at the takeover month
- `prepay_penalty`: `bridge_balloon × source.prepay_penalty_pct` (see §6.4)
- `perm_financing_costs`: sum of `_DEFAULT_LOAN_COSTS` for the perm funder type

**Cash flow injection:**
- Positive `net_refi` → "Refi — Net Proceeds to Equity" (inflow)
- Negative `net_refi` → "Refi — Equity Call (Shortfall)" (outflow)
- Bridge payoff, prepay penalty, and financing costs are each separate line items

**Perm sizing at stabilized NOI.** The perm's `dual_constraint` or `dscr_capped` sizing uses the engine's projected stabilized NOI (from income streams with escalation), not the going-in NOI. The cap rate for LTV defaults to the going-in cap but can be overridden via `source.refi_cap_rate_pct`. This is self-consistent: the only "invented" number is the deal's own NOI projection, which flows from the same income/expense assumptions used for every other metric.

### 2.11 Source-Use eligibility routing (Phase H, May 2026)

By default every capital source (CapitalModule) may fund any use line — the engine allocates draws from the full stack. Two optional whitelists restrict routing:

- **`capital_modules.eligible_use_tags` (`varchar[]`)** — if non-empty, this source may only fund use lines whose `cost_category` matches one of the listed tags.
- **`use_lines.eligible_module_ids` (`UUID[]`)** — if non-empty, this use may only be funded by the listed module IDs.

Both whitelists default to empty (permissive). The `app/engines/source_routing.py` module implements `eligible_sources_for_use()` and `route_use_to_sources()`. When no whitelist applies, the routing falls back to the legacy stack-position allocation unchanged.

#### 2.11.1 Capped-consumption grants (May 2026)

Grants and other fixed-amount sources (grant, forgivable_loan, tax_credit) behave as **capped consumption** when per-Use eligibility is configured:

- **`source.maximum` (JSONB key, Decimal)** — user-entered cap. Set when at least one Use references the source via `eligible_module_ids`.
- **`source.amount`** — engine-computed each compute pass when `maximum` is set. Equals `min(maximum, sum of eligible Use remaining buckets)`.

Resolution lives in [`app/engines/grant_caps.py`](../app/engines/grant_caps.py) — `resolve_grant_caps()` runs once at the top of `compute_cash_flows`, BEFORE `_auto_size_debt_modules`, so the gap-fill solver reads the correct grant contribution.

**Consumption order within a single grant** (deterministic):

1. Use start phase ascending (acquisition → construction → operation → stabilized)
2. Use amount descending (ties broken largest first within same phase)

**Multiple grants on the same Use** — `stack_position` ascending. Each grant decrements per-Use remaining buckets; later grants see only what earlier grants left behind. No pro-rata split.

**Timing derivation** — `active_phase_start` / `active_phase_end` are re-derived from the covered Uses on every compute:

- `active_phase_start` = earliest phase of any Use the grant consumed against
- `active_phase_end` = latest phase of any Use the grant consumed against (capped — phases past where the cap fills are not included)

**Under-utilization** — when `source.amount < source.maximum`, the S&U table renders the row yellow with a tooltip showing the unused balance.

**UI surfaces:**

- **Edit drawer** (`partials/model_builder_line_form.html`) — eligibility checklist + Amount/Maximum label toggle for `grant`, `forgivable_loan`, `tax_credit`, and `equity` (`_FIXED_AMOUNT` set, inherited from Source vehicle refactor May 2026).
- **Add wizard step 1** (`sw-step-1`) — same checklist appears once a fixed-amount type is selected; ticking ≥1 Use flips Amount → Maximum and `_swCheck` validates the active field.

**Edge cases:**

- Cap set but no eligibility selected → `source.amount = 0` (UI rejects this state at save; engine defends).
- All eligibility unchecked at save → `source.maximum` cleared, source reverts to legacy fixed-amount behavior.
- Use deleted → grant's eligibility list shrinks via `eligible_module_ids` referential cleanup; if it empties, grant reverts to legacy mode on next save.
- Use timing changes → grant's `active_phase_*` recomputes on next compute.

---

## 3. Reserves

> **2026-06 reserves-spec-align note.** This section was rewritten in
> June 2026 to reflect the spec-aligned reserve model that landed in
> commits `f2233ba` … `624210b`. The previous model used a `Lease-Up
> Reserve` (LUR-aware IR) plus a debugging-era `Cash Flow Support
> Reserve` (CFSR) sized from a bank-account proof. Both concepts are
> retired. The three reserves below now tile the timeline with no
> gaps by construction:
>
> | Reserve | Window |
> |---|---|
> | Interest Reserve (IR) | Debt Source Start → Stabilization |
> | Operating Deficit Reserve (ODR) | Lease-Up start → Stabilization |
> | Operating Reserve (OR) | Stabilization → end of model |
>
> The Stabilization milestone is now a runtime requirement (auto-
> created by `ensure_stabilization_milestone` on every builder load
> and backfilled by Alembic 0110 for pre-existing projects).

### Interest Reserve (IR) [investor, lender, app]

**Window.** Debt Source Start → Stabilization. Spans pre-development,
acquisition, construction, and lease-up phases under a single
umbrella. Multiple internal **sources of interest** (pre-dev loan,
acquisition loan, construction loan, lease-up accrual) are summed
inside the sizer; the writer collapses them into one
`Interest Reserve` UseLine so the user-facing S&U panel does not
balkanize a single concept.

**Formula — LUR-blind.**
```
IR = Σ_m=1..N  P × period_rate(m)
```
where `N = months between Source Start and Stabilization`,
`P = full funded principal` (the **lump** draw schedule, not the
legacy `(N+1)/2` linear average), and `period_rate(m)` is the
day-count-precise monthly rate from `app/engines/interest.py:period_interest_months()`.

**Critically, IR is *not* offset by Lease-Up Revenue (LUR).** The
lender's full interest is funded at Close, regardless of how the
operating curve ramps. Excess LUR during lease-up does not shrink
IR sized; it sweeps to **principal paydown** at runtime — see §6.5.

**Sizing/accrual basis identity.** The period loop accrues interest
on the **interest-bearing balance** (held flat at the original funded
principal) using the same `period_interest_months` helper that
sized IR. Under a zero-revenue counterfactual the cumulative
period-loop accrual exactly equals the sized IR pool. This is
locked by `tests/engines/test_reserves.py::test_interest_invariance_to_lur_sweep`.

**Why LUR-blind?** Per spec critique #2: if LUR netted against IR
sizing, then during the runtime period loop any revenue shortfall
would manifest as an IR over-draw (interest > funded IR), and the
lender would see late payment. LUR-blind sizing + DS-flat convention
+ sweep-to-principal collectively guarantee that the lender always
sees their full interest, and that excess revenue accrues to the
borrower's benefit via a smaller balloon — not via a smaller IR.

### Operating Deficit Reserve (ODR) [investor, lender, app]

**Window.** Lease-Up start → Stabilization. Only created when a
Lease-Up phase exists in the timeline.

**Formula — curve-driven.**
```
ODR = Σ_m in lease_up_window  max(OpEx(m) − LUR(m), 0)
```
where both `OpEx(m)` and `LUR(m)` come from the per-month operating
curves (occupancy ramp × stream rents on the income side; phase
ramps on the expense side). Months where revenue covers OpEx
contribute zero. The sum is balance-independent — it depends on the
operating curves, not on the principal — so it enters the
auto-sizing solve as a fixed Use, not a divisor term.

**ODR window is endogenous.** A slower absorption curve produces
both a **larger** ODR amount AND a **later** ODR end month. ODR is
not a fixed `R × month` rectangle; it is a curve-driven integral.
A scenario without a Lease-Up phase skips ODR entirely (acquisition
deals, turnkey rentals).

**Excess at window end.** Any unused ODR balance at Stabilization
sweeps to principal — same plumbing as the LUR sweep (§6.5).

**Replaces.** The legacy "Cash Flow Support Reserve" (CFSR) that
was sized post-hoc from a bank-account proof. ODR is sized from
the same curves the lender underwrites, not from a circular
self-funding feedback loop, so the auto-sizer converges in one
pass.

### Operating Reserve (OR) [investor, lender, app]

**Window.** Stabilization → end of model.

**Formula — parametrized basis.**
```
OR = R × basis(OR_basis_mode)
```
where `R = operation_reserve_months` (default 6) and
`basis(...)` is selected from `OperationalInputs.operation_reserve_basis`:

| `operation_reserve_basis` | basis |
|---|---|
| `ds` (default) | `DS_monthly` |
| `opex` | `OpEx_monthly` (stabilized) |
| `opex_plus_ds` | `DS_monthly + OpEx_monthly` (stabilized) |

**Simultaneous solve with IR when `OR_basis = ds`.** Per spec
critique #1, the `ds` basis makes OR principal-dependent (DS scales
with the loan), creating a second balance-dependent reserve on top
of IR-covers-IR. The auto-sizer's closed-form divisor folds both
terms into one expression (see §2.4 — the `1 − f_c − f_IR − f_OR`
denominator). When the closed form does not converge cleanly the
solver falls back to `newton_solve.solve_principal_for_dscr` with
both reserves recomputed per pass.

**Unused at end of model.** OR is held; released as part of the
exit cash flow at payoff.

### Stabilization milestone is required

All three reserve windows reference the Stabilization milestone. The
runtime service `app/services/stabilization_milestone.py:ensure_stabilization_milestone`
auto-creates one on every builder load when missing, anchored to
the natural predecessor (operation_lease_up > construction >
pre_development > close). Alembic 0110 backfilled all pre-existing
projects.

The bank-account proof (`_run_bank_account_proof`) extends to a
**Stabilization-anchor validator** (Slice 5d): it computes the
first operating-window month where `NOI ≥ DS` from the actual
curves — the curve-derived Stabilization point — and compares
against the user's anchor:

| Anchor vs curve | Result |
|---|---|
| Anchor earlier than curve | `status="error"` — IR window ends before NOI can carry DS; OR is absorbing what should still be IR coverage. Red banner. |
| Anchor later than curve | `status="warning"` — OR sized for longer runway than needed. Conservative; deal still pencils. |
| Anchor matches curve | No payload added. |

The validator does **not** block compute. It surfaces on the
Underwriting view via `OperationalOutputs.bank_account_proof.stabilization_anchor`.

### Plain English (all three)

> **IR.** "Cover every dollar of interest the lender wants from
> Source Start through Stabilization. Don't take credit for the
> rent that hasn't shown up yet."
>
> **ODR.** "Cover the months where OpEx is higher than the rent
> ramp can pay. Stop covering once Stabilization arrives — the
> deal can carry itself from then on."
>
> **OR.** "Park `R` months of cushion at Stabilization so the
> deal survives a quarter or two of bad performance without
> defaulting."

### Cash Flow Support Reserve (CFSR) [investor, lender, app]

**Status.** Retired as an auto-emitted reserve. CFSR remains in the
engine vocabulary as a **manual / per-scenario-allowlist** label so
legacy deals continue to load and per-deal LP requests can be
honored. New deals should size ODR (curve-driven) instead.

**Where it can still appear.** A `UseLine` carrying the label
`Cash Flow Support Reserve` is treated as balance-only (excluded
from TPC), carried as opening cash in the bank-account proof
(included in `bank_account_extractor._RESERVE_LABELS`), and
rendered on the S&U sheet under its own row with a named cell
`s_cfsr_amount`.

**Why retired.** CFSR was sized post-hoc from a bank-account-proof
shortfall, creating a circular self-funding loop that needed
multiple convergence passes. ODR sizes off the same operating
curves the lender underwrites and clears in one pass.

### Bank-Account Solvency Proof [investor, lender, app]

**Definition.** A period-level simulation that walks the bank
balance month by month from Day 0 (Close) through Stabilization
and verifies the balance never breaches the operating reserve
floor. Surfaces as `OperationalOutputs.bank_account_proof`.

**Reported fields (engine output).**
```
{
  "opening_cash":          Day-0 cash from reserve Uses,
  "min_balance":           lowest cash held over the window,
  "min_balance_date":      ISO date of the lowest-cash month,
  "max_shortfall":         largest dip below the reserve floor,
  "max_shortfall_date":    ISO date of the worst breach,
  "is_solvent":            True when no breach occurred,
  "co_period":             month index of Construction Completion,
  "stabilized_period":     month index of Stabilization,
  "months_simulated":      window length,
  "proof_start":           "day_0" | "co" | "stabilized",
  "stabilization_anchor":  user-vs-curve anchor validator (Slice 5d)
}
```

**Investor Summary tile.** The Excel export's Underwriting Summary
sheet aggregates across projects, picks the worst-case (lowest
`min_balance`) row, and emits the named cells
`s_bank_proof_min_balance`, `s_bank_proof_min_balance_date`, and
`s_bank_proof_is_solvent`. Insolvent rows additionally emit
`s_bank_proof_max_shortfall` and `s_bank_proof_max_shortfall_date`.

**Engine source.** `_run_bank_account_proof` in
`app/engines/cashflow.py`; window extraction in
`app/engines/bank_account_extractor.py`. Full math in Appendix G.

### Deferred Developer Fee Balance [investor, lender, app]

**Definition.** The unpaid portion of the Developer Fee that the
sponsor agrees to leave in the deal at Close, repaid from
operating cash flow per the waterfall. Persisted as
``OperationalOutputs.dev_fee_balance_series`` (Phase B, 2026-06-02).

**Schedule shape.**
```
{
  "opening_at_close":    str(Decimal),
  "fully_paid_period":   int | None,
  "total_paid":          str(Decimal),
  "remaining_at_horizon": str(Decimal),
  "periods": [
    {
      "period":                 int,
      "opening_balance":        str(Decimal),
      "paydown_from_waterfall": str(Decimal),
      "paydown_from_float_topup": str(Decimal),
      "closing_balance":        str(Decimal),
    }
  ]
}
```

**Excel surfaces (Underwriting Cash Flow).**
- ``r_uw_cf_ddf_balance`` — end-of-year closing balance, summed
  across projects. Y0 carries ``opening_at_close``. Years past
  ``fully_paid_period`` show $0.
- ``r_uw_cf_ddf_recovered`` — sum of ``paydown_from_waterfall +
  paydown_from_float_topup`` for periods inside each year.

**Engine source.** ``app/engines/dev_fee_balance.py``;
``OperationalOutputs.dev_fee_balance_series`` written by
``compute_waterfall``. Float-paydown contributions come via
``float_topups_by_milestone`` (Float Earnings Phase B).

### Float Earnings (Found Money) [investor, lender, app]

**Definition.** Treasury-yield earnings on a parent debt source's
drawn-but-unspent balance during construction. When a debt
module's ``balance_earns_interest=True``, the funded principal
sitting in the deposit account between Close and full deployment
earns interest at the user-entered ``yield_pct``. The accumulated
yield is then re-injected into the deal as a "Found Money"
source.

**Source schema.** A separate ``CapitalModule`` carries
``vehicle_type="float_earnings"``, ``source.parent_module_id``
pointing at the debt module, ``source.yield_pct`` (annual %), and
splits ``dev_fee_split_pct`` / ``debt_paydown_split_pct``
controlling where the accrued amount lands.

**Engine output.** ``OperationalOutputs.float_earnings_series``:
```
{
  "sources":             [{float_source_id, parent_module_id,
                            total_earnings, schedule[...]}],
  "found_money_periods": {str(period): float},
  "warnings":            [...]
}
```

**Excel surface.** ``r_uw_cf_float_earnings`` row on Underwriting
Cash Flow sums ``found_money_periods`` per year. The S&U Sources
block already renders each float-earnings ``CapitalModule`` as
its own row via the existing ``s_<slug>_principal`` mechanism —
no extra named cell needed.

**Engine source.** ``app/engines/float_earnings.py``;
``compute_scenario_float_earnings`` runs inside the cashflow
convergence loop. Phase B (commit ``dc4de2c``) routes operating
NCF through a ``deferred_developer_fee`` waterfall tier so the
``debt_paydown_split`` and ``dev_fee_split`` interact correctly.

### Acquisition Fee [investor, lender, app]

**Definition.** A separate sponsor fee paid at close, computed as a
percentage of the purchase price. Appears as its own UseLine when
``dev_fee_acquisition_treatment="separate_fee"`` on the auto Dev Fee
row; the engine maintains it via ``is_auto_acquisition_fee=True`` so
the amount re-derives whenever the purchase price changes.

**Calculation.**
```
acquisition_fee_amount = acquisition_fee_pct × purchase_price
```

**Excel surfaces.**
- ``s_acquisition_fee`` — first-occurrence cell in the S&U Acquisition
  cost section (auto Acquisition Fee rows render under Acquisition
  rather than Soft Costs, regardless of their stored ``cost_category``).
- ``s_acquisition_fee_pct`` — input percentage on Block A of the
  Assumptions sheet.

**Engine source.** ``app/engines/dev_fee.py``; the Acquisition Fee row
is created and maintained alongside the auto Dev Fee row whenever the
treatment is ``separate_fee``. Setting any other treatment deletes the
row.

### Dev Fee Caps (per Source) [investor, lender, app]

**Definition.** Each ``CapitalModule`` may carry a ``fee_terms``
JSONB rule that limits how much of the Developer Fee that source can
fund. The engine evaluates every source's allowable amount and the
lowest one becomes the **binding** cap — the source the deal would
hit first if Dev Fee were sized up.

**Cap kinds (any field optional — null means "no cap of this kind").**
- ``max_pct`` — maximum Dev Fee as a percentage of basis.
- ``per_unit_cap`` — maximum dollars per unit (residential).
- ``absolute_cap`` — a hard dollar ceiling.
- ``basis_inclusions_override`` / ``basis_exclusions`` — which cost
  buckets feed the basis for this source.

**Excel surface.** ``r_su_dev_fee_caps`` — table on the S&U sheet
under the Sources block, one row per CapitalModule with non-empty
``fee_terms``. Columns: Source, Max %, Per-Unit Cap, Absolute Cap,
Allowable $, Binding (✓/—). The binding row is rendered bold; the
binding source is read from
``UseLine.dev_fee_binding_context.binding_source_id``.

**Engine source.** ``app/engines/dev_fee.py`` — the multi-source
binding pipeline (``_compute_one_fee`` + binding selector). Per-source
allowables are persisted on the Dev Fee UseLine's
``dev_fee_binding_context.per_source_allocation``.

### Dev Fee Release Schedule [investor, lender, app]

**Definition.** Milestone-weighted disbursement plan for the
Developer Fee. Each weight is a fraction (0–1) tied to a milestone;
when that milestone clears, the engine releases ``weight × elected_fee``
in that period. A separate ``final_holdback`` releases its ``pct`` at
the chosen milestone. Sum of all ``weights[].weight + final_holdback.pct``
must equal 1.0 (validated at write and again before scheduling).

**Stored shape.** ``UseLine.dev_fee_release_schedule``:
```
{
  "weights": [{"milestone_id": UUID, "weight": Decimal}, ...],
  "final_holdback": {"milestone_id": UUID, "pct": Decimal}
}
```

**Excel surface.** ``r_su_dev_fee_release`` — table on the S&U sheet
under the Caps block, one row per weight plus a final holdback row.
Columns: Milestone, Weight %, Holdback %. Mini-block omitted when
schedule is empty (legacy "release at close" behavior).

**Engine source.** ``app/engines/dev_fee.py`` — the schedule drives
the timing entries on the auto Dev Fee row. The Assumptions sheet
cell ``s_dev_fee_final_holdback_pct`` mirrors the final-holdback
percentage for at-a-glance review.

### Retired reserve concepts

The following UseLine labels are no longer auto-emitted by the
engine. Alembic 0109 remaps any leftover `dev_fee_basis_bucket`
values to the new vocabulary; the labels themselves no longer
appear in `BASIS_BUCKETS`.

| Retired label | Replacement |
|---|---|
| `Lease-Up Reserve` | Subsumed into umbrella `Interest Reserve` |
| `Construction DS Reserve` | Subsumed into umbrella `Interest Reserve` |
| `Cash Flow Support Reserve` | `Operating Deficit Reserve` (curve-driven) |
| `Pre-Development Interest Reserve` | Subsumed into umbrella `Interest Reserve` |
| `Acquisition Interest Reserve` | Subsumed into umbrella `Interest Reserve` |
| `Construction Interest Reserve` | Subsumed into umbrella `Interest Reserve` |

The `_lease_up_carry` PI-amortization-during-lease-up code path
and the `Construction DS Reserve` UseLine writer are retained in
the engine but no longer fire for IR-carry loans on the new spec
(they remain as fallbacks for legacy non-IR PI loans). Their
removal is tracked as an open item.

---

## 4. Revenue / NOI

### Gross Revenue [investor, lender, app]

**Definition.** Sum of escalated stream amounts before vacancy, bad debt, and
concessions. Also called Gross Potential Rent (GPR) when all streams are rent.

**Calculation.**
```
gross_revenue = Σ escalated_stream_amount  (per period, summed across active streams)
```

**Engine source.** `_compute_period` in `app/engines/cashflow.py`.

**Notes / edge cases.** Only meaningful in `revenue_opex` mode. In `noi` mode,
the engine reports gross revenue equal to NOI by construction.

### EGI (Effective Gross Income) [investor, lender, app]

**Definition.** Gross revenue minus vacancy loss, bad debt, and concessions —
the income actually expected to be collected before operating expenses.

**Calculation.**
```
EGI = gross_revenue − vacancy_loss − bad_debt − concessions
```

**Engine source.** `_compute_period` in `app/engines/cashflow.py`.

**Floor invariant.** EGI is floored at zero. When `bad_debt + concessions > after_vacancy`
(e.g. full vacancy with non-zero deduction percentages), both are scaled down proportionally
so their sum equals `after_vacancy` exactly, preserving the accounting identity:

```
net_income + vacancy_loss + bad_debt + concessions == gross_revenue
```

**Notes / edge cases.** Bad debt and concessions are separate percentage
deductions from GPR (default 0%). They match the standard CRE pro forma
format and enable HelloData/CoStar feeds that supply them as distinct fields.

### NOI (Net Operating Income) [investor, lender, app]

**Definition.** EGI minus operating expenses minus CapEx reserve. The
income-statement bottom line above the debt-service deduction.

**Calculation.**
```
NOI = EGI − OpEx − CapEx_Reserve
```

In `noi` mode the user enters NOI directly and the engine applies an annual
escalation factor anchored at the first stabilized month (see §4.6).

**Engine source.** `_compute_period` writes monthly NOI into `CashFlow.noi`;
`OperationalOutputs.noi_stabilized` materializes the stabilized annual value.

**Notes / edge cases.** CapEx Reserve sits below NOI because it is a cash
deduction, not an accounting expense. The distinction matters: DSCR uses NOI
(excluding CapEx) while cash-on-cash uses distributable cash (including
CapEx). See §5.3.

### Stabilized NOI [investor, lender, app]

**Definition.** The first year's annualized NOI once lease-up has completed
and occupancy reaches `stabilized_occupancy_pct`.

**Calculation.**
```
stabilized_noi = NOI_monthly_at_first_stabilized_month × 12
```

**Engine source.** `OperationalOutputs.noi_stabilized` (per project), summed
across projects by `rollup_summary` for scenario-wide display.

**Excel formula (Phase 4 hero-KPI conversion, 2026-05-24).** The
Underwriting Summary "Combined Stabilized NOI" cell is now the hybrid
formula `=IF(s_pf_noi_y1>0, s_pf_noi_y1, <engine_fallback>)`. The
underlying `s_pf_noi_y1` named cell points at row Y1 of the Pro Forma
NOI line, which is itself a formula chain back to Block F (revenue) and
Block G (OpEx) inputs. LP edits to any single revenue stream or OpEx
line ripple through Pro Forma Y1 → this KPI without re-running the
engine. The engine value is preserved as the false-branch fallback so
pre-operational scenarios (where Pro Forma Y1 = 0) still surface the
modeled stabilized NOI.

The companion **Stabilized DSCR (combined)** cell is the related
formula `=IF(AND(s_pf_noi_y1>0, s_pf_debt_service_y1>0),
s_pf_noi_y1/s_pf_debt_service_y1, <engine_fallback>)` where
`s_pf_debt_service_y1` is row Y1 of the Pro Forma debt-service line
(a SUMPRODUCT over per-loan PMT/IPMT formulas — see §2.2).

**Notes / edge cases.** This is the NOI used by `dscr_capped` and
`dual_constraint` debt sizing modes. Drift between stabilized NOI used for
sizing and stabilized NOI computed in the cash flow loop is the reason the
`/compute` endpoint runs a fix-point iteration (§4.7).

### 4.1 Two income modes

`Scenario.income_mode` selects between:
- **`revenue_opex`** (default): sum `IncomeStream` rows minus `OperatingExpenseLine` rows → NOI
- **`noi`**: user enters stabilized NOI directly via `OperationalInputs.noi_stabilized_input`; engine applies an annual escalation factor

Both produce the same downstream math (DSCR, reserves, gap-fill). The difference is where NOI comes from.

### 4.2 Income streams (revenue_opex mode)

**Schema (deal.py:372):**
```python
class IncomeStream:
    unit_count: int | None
    amount_per_unit_monthly: Decimal | None
    amount_fixed_monthly: Decimal | None
    stabilized_occupancy_pct: Decimal      # default 95
    bad_debt_pct: Decimal                  # default 0 — % of GPR lost to bad debt
    concessions_pct: Decimal               # default 0 — % of GPR lost to concessions
    renovation_absorption_rate: Decimal | None  # if set, ramps premium 0→100% over reno+lease-up
    escalation_rate_pct_annual: Decimal    # default 0
    active_in_phases: list[str]            # e.g. ["lease_up", "stabilized"]
```

**Base amount per month:**
```
if amount_fixed_monthly is set:
    base = amount_fixed_monthly
else:
    base = amount_per_unit_monthly × unit_count
```

**Per-period computation:**
```
escalated = base × (1 + escalation_rate)^(period/12)

# Renovation absorption: if renovation_absorption_rate is set, ramp
# the premium linearly from 0→100% over reno + lease-up months
if renovation_absorption_rate > 0 and phase is reno/construction/lease-up:
    absorption = min(period + 1, reno_months + leaseup_months) / (reno_months + leaseup_months)
    escalated = escalated × absorption

after_vacancy = escalated × occupancy_pct_this_phase
vacancy = escalated − after_vacancy
bad_debt = escalated × bad_debt_pct
concessions = escalated × concessions_pct
# proportional cap: if bad_debt + concessions > after_vacancy, scale both down
# so net_income floors at 0 and accounting identity holds
if bad_debt + concessions > after_vacancy:
    scale = after_vacancy / (bad_debt + concessions)
    bad_debt = bad_debt × scale
    concessions = after_vacancy − bad_debt
net_income = after_vacancy − bad_debt − concessions  # >= 0
```

Summed across all active streams → gross_revenue, vacancy_loss, EGI.

**Bad debt and concessions** are separate percentage deductions from GPR, distinct from vacancy. Default to 0% (backward-compatible). These match the industry-standard CRE pro forma structure where vacancy, bad debt, and concessions are separate line items between GPR and EGI.

**Why `(1 + rate)^(period/12)`?** This is continuous annual escalation — `rate = 3%` compounds monthly at `(1.03)^(1/12) − 1 ≈ 0.247%`. At month 24 (two years in), the factor is `1.03^2 = 1.0609` exactly.

### 4.3 Occupancy ramp (lease-up)

**Formula:**
```
step = (stabilized_occ − initial_occ) / (months − 1)
occupancy_month_i = clamp(initial_occ + step × i, 0, stabilized_occ)
```

Where `initial_occ` defaults to 50% and `stabilized_occ` defaults to 95% (configurable per stream / per deal).

**Why 0% initial when NULL?** This is the `OperationalInputs.initial_occupancy_pct` field. In new construction it should be 0%; in acquisition-with-repositioning it should be ~60% (existing tenants retained). **As of 2026-06-03 the engine defaults NULL to 0%** (matching the wizard slider's default rendering and the slider label text "0% = new construction (no pre-leasing)"). Before that date the engine defaulted NULL to 50%, which produced a silent mismatch where the wizard slider rendered at 0 but the cash-flow loop ran the deal as if the slider were at 50 — surfaced on deal `cf0e77c3` when Operating Deficit Reserve sized at $0 despite an actual operating shortfall. The New Deal Wizard (collected since 2026-05-29) supplies an explicit value on the way in for all new deals; legacy deals on NULL now read 0%.

**Shared ramp helper (2026-06-03).** The lease-up occupancy formula lives in `app/engines/cashflow_compile.py:lease_up_ramp_occupancy` and is called from three call sites that previously had divergent implementations:

| Call site | What it scales | Pre-2026-06-03 behavior |
|---|---|---|
| `_stream_occupancy_pct` | Per-stream revenue occupancy | Read `lease_up_curve` (linear / s_curve) |
| `_compute_period` OpEx ramp | Per-line OpEx where `scale_with_lease_up = True` | **Always linear** regardless of slider |
| `_odr_pool` integral | OpEx side of `Σ max(OpEx − LUR, 0)` | **Always linear** regardless of slider |

Result of the divergence: an S-curve deal had revenue ramping S-shape while OpEx ramped linear, producing a shape mismatch that fed into Operating Deficit Reserve sizing. The shared helper aligns all three call sites — revenue, OpEx, and ODR now walk the same curve with the same `initial_occupancy_pct`, `stabilized_occupancy` (0.95), and `lease_up_curve_steepness` (default 5) inputs.

**S-curve option.** When `OperationalInputs.lease_up_curve = "s_curve"`, the ramp uses a logistic function instead of linear:

```
t_norm = month_index / (months - 1)           # 0.0 → 1.0
raw = 1 / (1 + e^(-k × (t_norm - 0.5)))       # logistic sigmoid
normalized = (raw - sigmoid(-k/2)) / (sigmoid(k/2) - sigmoid(-k/2))
occupancy = initial_occ + (stabilized_occ - initial_occ) × normalized
```

Where `k` = `lease_up_curve_steepness` (default 5; range 1=flat to 10=steep). At k=5 this produces the classic slow-start → rapid-middle → slow-finish absorption pattern observed in real lease-ups. The normalization ensures occ(0) = initial and occ(N) = stabilized exactly.

**When to use S-curve.** Large new-construction or major-reno projects where absorption follows a marketing-driven pattern. Keep linear (default) for smaller value-add deals where units turn one at a time.

### 4.4 Occupancy in hold / renovation phases

**Hold phase:** `stabilized_occ × (1 − hold_vacancy_rate_pct)` — user-specified vacancy during the hold period (e.g., while planning renovations).

**Renovation phase:** `stabilized_occ × (1 − income_reduction_pct_during_reno)` — user-specified income hit during renovations.

### 4.5 Renovation absorption rate (value-add premium phase-in)

When `renovation_absorption_rate` is set on an income stream, the stream's escalated amount is scaled by an absorption fraction that ramps linearly from 0 to 1 over the combined renovation + lease-up timeline:

```
total_abs_months = renovation_months + lease_up_months
absorption_frac = min(current_period + 1, total_abs_months) / total_abs_months
escalated_amount = escalated_amount × absorption_frac
```

**Why this matters for value-add deals.** In a 200-unit renovation where you're adding a $200/mo premium, not all units come online at once. Without absorption, the pro forma shows full premium from day one — overstating Year 1-2 revenue, which directly affects:
- Leveraged IRR (very sensitive to early-period cash flows)
- DSCR during the ramp period (could show false covenant breach)
- Draw schedule sizing (lower early cash flow = more reserves needed)

**When to use.** Set `renovation_absorption_rate = 1.0` on premium-driven income streams for value-add deals. Leave it `NULL` (default) for acquisition deals where income is already stabilized.

**Discrete capture schedule (engine only — not exposed in UI).** The engine supports `renovation_capture_schedule` as a JSON array of `{year, capture_pct}` entries for PropRise-style discrete steps. However, the UI exposes only the continuous ramp (`renovation_absorption_rate`). The discrete schedule is available for API/import use but is not a primary modeling path. Continuous ramp is simpler to configure and produces smoother cash flows.

### 4.7 LTL Catchup Escalation

When an income stream has `catchup_target_rent` set, the engine applies accelerated escalation capped at `LTL_CATCHUP_CAP_PCT` (hardcoded 10%) per year until the target is reached, then reverts to normal `escalation_rate_pct_annual`.

**Formula (per year):**
```
if current_rent < catchup_target_rent:
    increase = min(target - current, current × 0.10)
    current = current + increase
else:
    current = current × (1 + normal_escalation_rate)
```

**Example** ($1,200 in-place → $1,500 market, 10% cap, 3% normal):
```
Year 0: $1,200 (in-place)
Year 1: $1,200 + min($300, $120) = $1,320  (10% cap binds)
Year 2: $1,320 + min($180, $132) = $1,452  (10% cap binds)
Year 3: $1,452 + min($48, $145)  = $1,500  (gap closed, full amount < cap)
Year 4: $1,500 × 1.03            = $1,545  (normal escalation resumes)
```

**Partial-year interpolation.** Within a year, the catchup increase is pro-rated by month: `increase × (month_in_year / 12)`. This preserves monthly granularity.

**Why 10% cap?** A 10% annual rent increase is at the upper end of what the Portland multifamily market can absorb without mass turnover. Higher increases (15-20%) are theoretically possible but cause vacancy spikes that offset the revenue gain. The cap is a global constant (`LTL_CATCHUP_CAP_PCT`) — not user-configurable — to enforce realistic modeling.

**Relationship to renovation absorption.** LTL catchup and renovation absorption are independent and apply to different unit pools:
- **LTL catchup** applies to units NOT being renovated — closing the gap between in-place and market rent through lease renewals
- **Renovation absorption** applies to units being renovated — phasing in the post-renovation premium as units are turned

For units in the value-add pool, renovation supersedes LTL: the unit goes directly from `in_place_rent` to `post_reno_rent`. The LTL gap ($300 in the example) is captured implicitly because `post_reno_rent` ($1,800) already exceeds `market_rent` ($1,500).

### 4.8 Unit Strategy Assignment (unit_mix JSONB)

> **Storage (migration 0072):** `unit_mix` is now a JSONB column on `Project` (not a standalone DB table). Each element is a dict with the fields below. Deep-copied from the Opportunity at Project creation. Edit inside a Deal never writes back to the Opportunity.

| Strategy | Driving Fields | Rent Trajectory |
|---|---|---|
| `base_escalation` | `in_place_rent_per_unit` | `in_place` → normal annual escalation |
| `ltl_catchup` | `in_place_rent_per_unit`, `market_rent_per_unit` | `in_place` → accelerated (cap 10%/yr) to `market_rent` → normal |
| `value_add_renovation` | `post_reno_rent_per_unit`, `renovation_absorption_rate` | `in_place` → renovation → `post_reno_rent` → normal |

**UnitMix schema fields (April 18 2026):**

| Field | Type | Notes |
|---|---|---|
| `label` | str | Display label (e.g., "1BR/1BA") |
| `unit_count` | int | Number of units of this type |
| `avg_sqft` | Numeric(18,2) | Average square footage |
| `beds` | Numeric(4,1) | Bedrooms: 0, 1, 2, 3, 4, 5+ (5 represents "5 or more") |
| `baths` | Numeric(4,1) | Baths in 0.5 increments: 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5+ |
| `in_place_rent_per_unit` | Numeric(18,2) | Current tenant rent (loss-to-lease anchor) |
| `market_rent_per_unit` | Numeric(18,2) | Market rent (LTL target + property value basis) |
| `post_reno_rent_per_unit` | Numeric(18,2) | Post-renovation rent (value-add strategy only) |
| `unit_strategy` | str | `base_escalation` / `ltl_catchup` / `value_add_renovation` |

**Removed April 18 2026**: `avg_monthly_rent` (legacy). It duplicated `in_place_rent_per_unit` semantically and created ambiguity. Migration 0046 drops the column. Bed/bath were added as numeric variables so comp-data ingestion (HelloData, etc.) can populate them directly.

**Derived building totals (Excel export inputs, May 12 2026):**

| Total | Source | Notes |
|---|---|---|
| Total units | `Σ unit_mix[].unit_count` | Captured per row at pro forma import or in the unit-mix editor |
| Net rentable sq ft | `Σ (unit_mix[].unit_count × unit_mix[].avg_sqft)` | Computed at read time; no separate column |
| Gross building sq ft | **stubbed** | No active capture path. Previously collected via the wizard's "Building Data Needed" step (removed 2026-05-12). Re-introduce when a workflow needs it; Excel exports currently leave the cell blank or echo net rentable. |

**Apply to Revenue** (endpoint: `POST /ui/models/{id}/unit-mix/apply-to-revenue`) auto-generates IncomeStream rows per unit type:
- `ltl_catchup` units → stream with `catchup_target_rent = market_rent_per_unit`, base = `in_place_rent_per_unit`
- `value_add_renovation` units → stream labeled `"{unit} Rent (Renovated)"` with `renovation_absorption_rate = 1.0`, base = `post_reno_rent_per_unit or market_rent_per_unit or in_place_rent_per_unit`
- `base_escalation` units → stream with standard escalation only, base = `in_place_rent_per_unit or market_rent_per_unit`

Idempotent — re-running replaces matching-labeled streams, preserves one-off streams (parking, laundry, etc.). Only available in `revenue_opex` mode; hidden in `noi` mode.

### 4.6 NOI-mode direct input

```python
_noi_annual = _to_decimal(inputs.noi_stabilized_input)
_esc_period = max(0, period - first_stab_period)  # anchored at first stabilized month
_esc_factor = _growth_factor(inputs.noi_escalation_rate_pct or Decimal("3"), _esc_period)
_noi_monthly = _q(_noi_annual / Decimal("12") * _esc_factor)
```

Applied month-by-month in stabilized/lease-up/exit phases. Construction phases see `_noi_monthly = 0`.

**Escalation anchor (important — April 18 2026).** Escalation is anchored at `first_stab_period` (the month index of the first stabilized period), **not** at deal month 0. Semantics: the user-entered `noi_stabilized_input` is the NOI at **year 1 of stabilization**, the underwriting convention. Previously the engine applied escalation from deal month 0, so a 22-month construction/lease-up timeline lifted the displayed first-stabilized-month NOI above the raw input by `(1+rate)^(22/12)`. This caused DSCR in `dscr_capped` / `dual_constraint` sizing to drift above the minimum (e.g. 1.1557 instead of 1.15) because sizing used the raw input but display used the escalated value.

With the anchor fix:
- First stabilized month: `esc_period = 0` → `esc_factor = 1.0` → NOI = raw input
- Year 2 of stabilization: `esc_period = 12` → `esc_factor = (1+rate)^1`
- Lease-up months (if any, period < first_stab_period): clamped to 0 via `max(0, ...)` → factor = 1.0 (simplification — lease-up NOI isn't modeled separately in NOI mode)

The `first_stab_period` is computed once in the main compute loop from the phase plan and passed into `_compute_period`.

### 4.7 Fix-point iteration for DSCR convergence

When `debt_sizing_mode` is `dscr_capped` or `dual_constraint`, the **first** sizing pass within a compute can only use an **estimated** stabilized NOI (from `_estimate_stabilized_noi_monthly`) or a `prev_noi_stabilized` from a prior compute. The estimator misses escalation carry-in and capex reserve deductions; `prev_noi_stabilized` is stale if inputs changed. Either way, the NOI used for sizing may differ from the NOI the compute ultimately produces, causing DSCR to drift above the target minimum.

The `POST /api/models/{id}/compute` endpoint wraps `compute_cash_flows` in a fix-point loop:

```python
MAX_ITERATIONS = 5
DSCR_CONVERGENCE_TOLERANCE = Decimal("0.005")
for _iter in range(MAX_ITERATIONS):
    result = await compute_cash_flows(...)
    if sizing_mode not in {"dscr_capped", "dual_constraint"}:
        break
    cur_dscr = result.get("dscr")
    if prev_dscr is not None and abs(cur_dscr - prev_dscr) < TOLERANCE:
        break
    prev_dscr = cur_dscr
```

The iteration loop lives in the **compute endpoint** (`app/api/routers/models.py`), not inside `cashflow.py`. The cashflow engine runs a single pass — it accepts inputs and returns results. The endpoint calls `compute_cash_flows()` up to 5 times, each time feeding the prior pass's `OperationalOutputs.noi_stabilized` into the next pass's auto-sizer. This is why the constants `MAX_ITERATIONS` and `DSCR_CONVERGENCE_TOLERANCE` belong to the endpoint, not the engine.

Each iteration reads the **previous** `OperationalOutputs.noi_stabilized` (via the code at line 116 of `cashflow.py`) and passes it to `_auto_size_debt_modules` as `prev_noi_stabilized`. Iteration N+1 sizes using iteration N's actual computed NOI, so by iteration 2–3 the sized debt service matches the final NOI and DSCR converges.

- **Convergence tolerance**: 0.005× (half a basis point of DSCR).
- **Iteration cap**: 5. If math doesn't converge (shouldn't happen — NOI is debt-independent so convergence is in 2 passes), the 5th iteration's result is returned as-is.
- **Performance**: typical deals run in 2 iterations (~600ms–1s total). Cap of 5 bounds worst case at ~3s.
- **Observability**: `result["sizing_iterations"]` surfaces the count used (exposed to logs and the frontend).

Note: `gap_fill` mode doesn't iterate — only sizes once.

---

## 5. Operating Expenses

### 5.1 Stabilized OpEx (pre-compute)

Before the cash flow loop runs, we sum up stabilized OpEx to use in reserve sizing:

```python
opex_monthly_pre = ZERO
for line in expense_lines:
    active = {str(phase) for phase in (line.active_in_phases or [])}
    if "stabilized" in active:
        opex_monthly_pre += _q(_to_decimal(line.annual_amount) / Decimal("12"))
```

This feeds the `max(OpEx, DS)` computation in the operating reserve (§3.1).

### 5.2 Per-period OpEx

Each month in the cash flow loop, for each expense line active in the current phase:

```
line_growth = (1 + escalation_rate)^(period/12)
line_base = (annual_amount / 12) × line_growth

if phase is lease_up and line.scale_with_lease_up:
    lease_up_scale = clamp(occupancy_ramp_this_month, floor_pct, 1.0)
    line_amount = line_base × lease_up_scale
else:
    line_amount = line_base
```

**Why `scale_with_lease_up` and `lease_up_floor_pct`?** Some expense lines (utilities, trash, leasing commissions) scale directly with occupancy — `scale_with_lease_up = True`, `lease_up_floor_pct = 0`. Others (property taxes, insurance, base salaries) are fixed — `scale_with_lease_up = False`, they stay at 100% regardless. Some are in between (maintenance at 50% minimum even when empty) — `scale_with_lease_up = True, lease_up_floor_pct = 0.5`.

The default when creating a new expense line is `scale_with_lease_up = False` (conservative: costs show at full during lease-up). Users opt in to lease-up scaling.

**Ramp curve consistency (2026-06-03).** When `scale_with_lease_up = True`, the OpEx ramp now calls the shared `lease_up_ramp_occupancy` helper in `app/engines/cashflow_compile.py` — the same helper that drives revenue occupancy and ODR sizing. Result: if the slider is set to S-curve, both revenue and OpEx ramp on the S-curve; if linear, both ramp linearly. Prior to this change, revenue honored the slider while OpEx always ran linear, producing a shape mismatch on S-curve deals.

### 5.3 Standard OpEx categories

All expense lines carry a `category` label drawn from `STANDARD_OPEX_CATEGORIES` in `app/models/deal.py`. The investor export groups lines by exact category label; the pro forma import parser maps arbitrary source labels to this vocabulary.

| Category | Typical contents |
|---|---|
| Real Estate Taxes | Property tax, special assessments |
| Insurance | Property & liability premiums |
| Jurisdiction Fees | Municipal levies — Gresham Police/Fire/Parks, city assessments |
| Property Management | On-site and off-site management fees |
| Utilities — Water/Sewer | Water, sewer, stormwater |
| Utilities — Electric | Common-area and unit electric |
| Utilities — Gas | Natural gas |
| Utilities — Trash | Garbage removal, recycling |
| Repairs & Maintenance | Routine repairs, elevator, general maintenance |
| Marketing & Leasing | Advertising, leasing commissions |
| Administrative | Office supplies, postage, printing |
| Payroll | Salaries, benefits, payroll taxes |
| Landscaping & Snow Removal | Grounds maintenance, snow removal |
| Pest Control | Pest and rodent treatment |
| Cleaning & Janitorial | Common-area cleaning |
| Security | Security monitoring, guard service |
| Resident Services | Tenant events, social services, resident programming |
| Legal | Legal fees, professional fees, licenses |
| Source Compliance | Funder monitoring fees — LIFT, OHCS, bond covenant reporting, HUD compliance |
| Bank/Software Fees | Bank service charges, property management software |
| Unit Turnover | Turnover cleaning, paint, minor repairs between tenants |
| Other | Catch-all for items not fitting above |

`"Other"` is the catch-all. The investor export groups by this exact label; typos create orphan groups. The pro forma import parser targets these labels for its confidence-scored mapping.

### OER (Operating Expense Ratio) [investor, lender, app]

**Definition.** Operating expenses divided by effective gross income —
the standard CRE operating-efficiency metric. Lower is better.

**Calculation.**
```
OER_period = operating_expenses_period / effective_gross_income_period
```

**Engine source.** Computed inline by the investor export from
`CashFlow.operating_expenses` and `CashFlow.effective_gross_income`
per annual bucket. Not stored as a single column on `OperationalOutputs`.

**Notes / edge cases.** Multifamily benchmarks: 35-45% is typical, 50%+ is
a yellow flag for the LP / lender. Returns "—" in the export when EGI = 0
(pre-stabilization periods).

### Yield on Cost [investor, lender, app]

**Definition.** Stabilized NOI divided by Total Project Cost — the asset's
unlevered earnings rate against what it cost to acquire/build. Headline
"is this deal reasonable on its own?" check.

**Calculation.**
```
yield_on_cost = NOI_stabilized / TPC
```

**Engine source.** Computed inline by the investor export's Underwriting
Summary "Property Valuation" section from `OperationalOutputs.noi_stabilized`
(summed across projects) and `OperationalOutputs.total_project_cost`.

**Notes / edge cases.** Equivalent to "going-in cap rate on cost." Compare
against the going-in market cap rate (`OperationalInputs.going_in_cap_rate_pct`)
to read the deal's yield premium / discount — see Cap Spread.

### Going-In Cap Value [investor, app]

**Definition.** Property value implied by capping stabilized NOI at the
going-in (acquisition) cap rate — the analyst's market valuation snapshot
at deal close.

**Calculation.**
```
going_in_cap_value = NOI_stabilized_combined / going_in_cap_rate
```

**Engine source.** Computed inline by the investor export's Property
Valuation section from `OperationalOutputs.noi_stabilized` and
`OperationalInputs.going_in_cap_rate_pct`.

**Notes / edge cases.** Differs from Direct Cap Value (Exit Cap basis)
only when the analyst sets going-in and exit cap rates differently, e.g.
modeling cap-rate decompression on exit. Common conservative pattern:
exit cap > going-in cap by 25-50 bps.

### Cap Spread [investor, lender, app]

**Definition.** Yield on Cost minus Going-In Cap rate — the deal's yield
premium (or discount) relative to the market cap input.

**Calculation.**
```
cap_spread = yield_on_cost − going_in_cap_rate
```

**Engine source.** Computed inline by the investor export's Property
Valuation section.

**Notes / edge cases.** Positive spread → buying below-market cap (yield
premium); negative → above-market acquisition price relative to NOI. A
spread of 100-200 bps is typical for value-add multifamily; below 50 bps
the deal needs cap compression or NOI growth to clear hurdle returns.

### Risk-Free Rate [investor, app]

**Definition.** The annualised risk-free benchmark rate (typically the
10-year US Treasury yield) at the time of underwriting. Used as the
denominator benchmark in the Spread Stack KPIs on the Underwriting
Summary sheet.

**Engine source.** `Scenario.risk_free_rate_pct` (nullable; falls back to
`settings.default_risk_free_rate_pct` = 4.25% when NULL). Set in the
Model Settings drawer.

**Notes / edge cases.** Scenario-level input, not a computed output. A
stale rate can make spreads misleading — update this when underwriting a
new deal if the rate environment has shifted materially.

### Cap Rate Spread [investor, app]

**Definition.** Going-in cap rate on cost minus the risk-free rate — the
unlevered risk premium the property earns over a T-bill.

**Calculation.**
```
cap_rate_spread = yield_on_cost − risk_free_rate
```

**Engine source.** Excel formula (Phase 4): the Cap Rate Spread cell on
Underwriting Summary is written as `=IFERROR(s_spread_cap_pct-s_rfr_pct,0)`.
`s_spread_cap_pct` is itself the formula `=IFERROR(s_combined_noi/s_total_project_cost,0)`,
so an LP edit to revenue / OpEx / Use lines re-derives NOI + TPC upstream
and the spread row follows without re-running the engine.

**Notes / edge cases.** A cap rate spread of 150–250 bps over the 10Y
Treasury is typical for stabilised multifamily. Below 100 bps the deal's
unlevered return offers little cushion vs. a risk-free alternative.

### Levered IRR Spread [investor, app]

**Definition.** Levered IRR minus a benchmark rate — quantifies the
return premium engineering (leverage + execution) delivers over a passive
benchmark. Two variants appear in the Spread Stack:

- **vs Cap Rate** (`s_irr_spread`): how much leverage adds to the
  unlevered going-in cap.
- **vs RFR** (`s_irr_rfr_spread`): total levered return premium over the
  risk-free rate.

**Calculation.**
```
irr_spread_vs_cap   = levered_irr − yield_on_cost
irr_spread_vs_rfr   = levered_irr − risk_free_rate
```

**Engine source.** Excel formula (Phase 4): both IRR Spread cells on
Underwriting Summary are written as formulas referencing
`s_combined_irr` (from the Primary KPI block, sourced from
`OperationalOutputs.levered_irr` via `rollup_summary`):

```
s_irr_spread      = =IFERROR(s_combined_irr-s_spread_cap_pct,0)
s_irr_rfr_spread  = =IFERROR(s_combined_irr-s_rfr_pct,0)
```

**Notes / edge cases.** Negative IRR vs Cap spread means leverage is
dilutive — the deal would return more unlevered. A positive spread of
200–400 bps over cap rate is a reasonable leverage hurdle for
value-add multifamily.

### Direct Cap Value [investor, app]

**Definition.** Property value implied by capping stabilized NOI at the
exit cap rate — the textbook valuation reconciliation against a DCF.

**Calculation.**
```
direct_cap_value = NOI_stabilized_combined / exit_cap_rate
```

**Engine source.** Computed inline by the investor export's Underwriting
Summary "Valuation Reconciliation" section from
`OperationalOutputs.noi_stabilized` (summed across projects) and
`OperationalInputs.exit_cap_rate_pct`.

**Notes / edge cases.** Should land within a few percent of the Modeled
Exit Value (engine-written sale events at the exit period). A wide delta
flags either the Exit Cap input or the underlying CF projection.

### Modeled Exit Value [investor, app]

**Definition.** Sum of `Sale` / `Exit`-prefixed `CashFlowLineItem` rows
in the exit period(s) — the engine's DCF-derived sale proceeds.

**Calculation.**
```
modeled_exit_value = Σ CashFlowLineItem.net_amount
                       where label.startswith("Sale" | "Exit")
```

**Engine source.** Synthesized in `_compute_capital_events_for_phase`
when `period_type == PeriodType.exit`; the export aggregates them across
projects.

**Notes / edge cases.** Compared against Direct Cap Value in the
Valuation Reconciliation section. Both numbers should converge if the
exit cap matches the implied DCF discounting; divergence is intentional
when the analyst has set `refi_cap_rate_pct` separately.

### Operating Expenses (OpEx) [investor, lender, app]

**Definition.** Recurring operating costs of the property — taxes, insurance,
property management, utilities, repairs, payroll. Sits between EGI and NOI on
the P&L.

**Calculation.**
```
opex_period = property_tax + insurance + opex_per_unit
            + Σ itemized_OperatingExpenseLine.amount
            + management_fee + carrying_cost
```

**Engine source.** `CashFlow.operating_expenses` (per project, per month).
Itemized rows live in `OperatingExpenseLine` and are summed in the engine's
per-period loop.

**Notes / edge cases.** OpEx differs from CapEx Reserve: OpEx hits the P&L
NOI line (DSCR uses NOI ÷ DS), CapEx is a below-NOI cash deduction (cash-on-
cash includes CapEx, DSCR doesn't). OpEx scales with occupancy when
`scale_with_lease_up = True`, with a configurable floor (`lease_up_floor_pct`)
for partially-fixed costs.

### CapEx Reserve [investor, lender, app]

```python
capex_reserve = (
    _q((_to_decimal(inputs.capex_reserve_per_unit_annual) * units / Decimal("12")) * expense_growth)
    if phase.period_type in {lease_up, stabilized, exit}
    else ZERO
)
```

**Plain English.** Per-unit annual CapEx reserve × unit count / 12, escalated by the expense growth rate, applied in operational phases only. This is a below-the-NOI-line deduction that reduces distributable cash but does not hit the P&L NOI figure.

**Why below-NOI and not an OpEx line?** CapEx reserves are a cash deduction, not an accounting expense. The distinction matters for DSCR (calculated on NOI, which excludes CapEx) vs. cash-on-cash returns (calculated on distributable cash, which includes CapEx).

---

## 6. Period Cash Flow (`_compute_period`)

Each month of the project runs through this calculation:

```
1. Gross Revenue        = Σ escalated_stream_amounts
2. Vacancy Loss         = Σ (escalated − net_income) per stream
3. EGI                  = Gross Revenue − Vacancy Loss
4. OpEx                 = property_tax + insurance + opex_per_unit + Σ itemized_lines + mgmt_fee + carrying_cost
5. CapEx Reserve        = capex_per_unit × units × growth / 12  (operational phases only)
6. NOI                  = EGI − OpEx − CapEx Reserve
7. Debt Service         = construction_debt_monthly or operation_debt_monthly (by phase)
8. Capital Outflows     = Σ use_line_amounts active this month
9. Capital Inflows      = exit-phase inflows (sale proceeds)
10. Net Cash Flow       = NOI − DS − Capital Outflows + Capital Inflows
```

### 6.1 UseLine timing: `first_day` vs `spread`

```python
if ul_timing == "spread":
    monthly_amount = total_amount / phase.months
    # last month picks up the rounding remainder
    if month_index == phase.months - 1:
        monthly_amount = total_amount - (monthly_amount × (phase.months − 1))
else:  # first_day
    if month_index != 0: continue
    amount = total_amount
```

**Plain English.** `first_day` drops the full amount on month 1 of its phase (used for closing costs, deposits, lump-sum payments). `spread` divides the amount evenly across all months of the phase (used for hard construction costs, ongoing soft costs).

### 6.2 Construction vs operation debt service

```python
debt_service = (
    construction_debt_monthly
    if phase.period_type in _CONSTRUCTION_PERIOD_TYPES
    else operation_debt_monthly
)
```

Where `_CONSTRUCTION_PERIOD_TYPES = {acquisition, hold, pre_construction, construction, minor_renovation, major_renovation, conversion}`.

This lets a single loan charge IO during construction and P&I during operations (the `io_then_pi` carry pattern). The two monthly figures are computed once at sizing time from the carry config.

### 6.3 Cash balance seeding invariant

```python
cumulative_cash_flow = total_sources  # period 0

for each period:
    ncf = compute_period(...)
    if is_stabilized and not seeded:
        cumulative_cash_flow = operating_reserve_amount   # reset
        seeded = True
    elif seeded:
        if ncf < 0:
            cumulative_cash_flow += ncf   # drain only on negative NCF
    else:
        cumulative_cash_flow += ncf       # pre-seed: accumulate everything
```

**What this enforces.** Pre-stabilization, the cash balance carries the running net of sources and uses — it can go negative, triggering equity calls in the waterfall. At first stabilized month, it resets to exactly the operating reserve (the gap-fill math guarantees this). Post-stabilization, positive NCF is distributable (not banked) and negative NCF drains the reserve.

**Why not carry forward post-stabilization NCF?** Because positive post-stabilized NCF goes out to investors through the waterfall. If we also added it to the cash balance, we'd be double-counting.

### 6.4 Prepay penalty at exit

At exit (sale), any debt module with `source.prepay_penalty_pct > 0` incurs a prepay penalty computed on the remaining balloon balance:

```
balloon = _balloon_balance(principal, rate, amort_years, total_hold_months, io_months)
prepay_cost = balloon × prepay_penalty_pct / 100
```

This is injected as a capital event line item ("Prepay Penalty — {label}") in the exit period, reducing net cash flow. Bridge modules (`is_bridge = True`) are excluded — their prepay is handled at refi (§2.10).

### 6.5 Refi capital events

When a bridge→perm takeout is detected (§2.10), the following line items are injected at the first month of the perm's active phase:

| Line Item | Direction | Amount |
|---|---|---|
| Refi — Bridge Payoff | outflow | bridge balloon balance |
| Refi — Prepay Penalty | outflow | bridge balloon × prepay_pct (if > 0) |
| Refi — Financing Costs | outflow | perm closing costs |
| Refi — Net Proceeds to Equity | inflow | surplus (if positive) |
| Refi — Equity Call (Shortfall) | outflow | deficit (if negative) |

---

## 7. Waterfall & Profit Metrics

**Waterfall style: American.** Distributions are computed period-by-period (cash distributed as earned, not held until exit). This is the industry standard for US multifamily syndications and JV structures.

### Cap Rate (Going-In) [investor, lender, app]

**Definition.** Year-1 NOI divided by total project cost — the
return-on-cost rate the lender and LP both check against market caps.

**Calculation.**
```
going_in_cap_rate = NOI_year_1 / TPC
```

**Engine source.** Computed for display by `rollup_summary`; `OperationalInputs`
carries `going_in_cap_rate_pct` as an analyst input on direct-NOI deals.

**Notes / edge cases.** Year-1 NOI may be negative or low if the project is
still in lease-up during the first 12 months. Stabilized cap (year-1 of
stabilization NOI ÷ TPC) is the more comparable number for value-add deals.

### Exit Cap Rate [investor, lender, app]

**Definition.** The cap rate applied to exit-year NOI to derive the sale
value of the asset.

**Calculation.**
```
months_to_exit   = exit_period - first_stabilized_period
NOI_at_exit      = stabilized_noi_monthly
                   × (1 + noi_escalation_rate_pct/100) ^ (months_to_exit/12)
                   × 12
exit_value       = NOI_at_exit / exit_cap_rate
```

`stabilized_noi_monthly` is the NOI at the *first* stabilized period (year-1
anchor). The engine grows it forward to the exit period using
`noi_escalation_rate_pct` regardless of income mode (`revenue_opex` or
`noi`). This means the sensitivity matrix correctly produces distinct IRR
values across the rent-growth axis — the exit price changes as NOI growth
changes.

**Engine source.** `OperationalInputs.exit_cap_rate_pct` and
`OperationalInputs.noi_escalation_rate_pct` (default 3%), used by
`_phase_capital_events` in `cashflow.py`.

**Notes / edge cases.** Default LTV property value uses the *going-in* cap; refi
LTV uses `source.refi_cap_rate_pct` when set, otherwise falls back to the
exit cap. Conservative convention: assume no cap-rate compression unless the
analyst explicitly models it. The Underwriting Summary "Valuation
Reconciliation" block uses year-1 `NOI_stabilized` (not the escalated exit
NOI) — that is intentional; it shows the going-in direct-cap value as a
cross-check, not the modeled exit price.

### DSCR (Debt Service Coverage Ratio) [investor, lender, app]

**Definition.** Stabilized annual NOI divided by stabilized annual debt
service — the lender's primary coverage metric.

**Calculation.**
```
DSCR = NOI_stabilized_annual / (operation_debt_monthly × 12)
```

**Engine source.** `OperationalOutputs.dscr` (per project). The cashflow
engine writes the initial value using the junction-overlaid principal.
`_apply_levered_metrics` in `waterfall.py` recomputes DSCR for the default
project only, using the cashflow engine's authoritative `debt_service` values
from `CashFlow` rows — it does not use `WaterfallResult.cash_distributed`
from the `debt_service` tier. Non-default projects retain the cashflow-engine
value unchanged.

**Notes / edge cases.** Lenders typically require ≥ 1.20–1.25. DSCR is per
loan, so multi-debt scenarios surface a worst-case across modules.
`PLACEHOLDER_DSCR = 1.25` is the engine fallback when `CapitalModule.source.dscr_min` is unset on the perm-debt module being sized.

### LTV (Loan-to-Value) [investor, lender, app]

**Definition.** Total non-bridge debt divided by stabilized property value.
Bridge modules are excluded to avoid double-counting with the perm that takes
them out.

**Calculation.**
```
property_value = NOI_stabilized / exit_cap_rate
LTV = total_non_bridge_debt / property_value
```

**Engine source.** LTV appears in two places: (1) inside the `dual_constraint` sizing loop in `cashflow.py` — the engine computes `P_ltv = (NOI / cap_rate) × LTV%` during auto-sizing and uses it as a principal ceiling; (2) at status-pill render time in `ui.py` (`_compute_calc_status`) for the informational display above the model builder. The metric value shown to the user is the render-time computation; the sizing-loop value is an intermediate that affects the resulting principal but is not stored as a separate output column.

**Notes / edge cases.** Per-loan LTV caps live on
`CapitalModule.source.ltv_pct`, NOT on a top-level `OperationalInputs`
column. (Wizard staging mirror at `inputs.debt_terms.{funder_type}.ltv_pct`
exists for re-edit population only.) Default LTV when absent is funder-
type-specific (typically 70% for acquisition, 75% for perm). In
`dual_constraint` sizing, LTV is one of three binding constraints (LTV /
DSCR / gap-fill).

### Debt Yield [lender, app]

**Definition.** Stabilized NOI divided by total non-bridge debt balance — a
coverage metric independent of interest rate and amortization.

**Calculation.**
```
debt_yield_pct = (NOI_stabilized / total_outstanding_debt_balance) × 100
```

**Engine source.** `OperationalOutputs.debt_yield_pct` (computed alongside
DSCR in the cashflow engine).

**Notes / edge cases.** Lenders increasingly use this as the primary coverage
gate. A 10% debt yield means NOI covers 10% of the loan balance annually;
most institutional lenders require 8–10% minimum.

### Asset Management Fee [investor, app]

**Definition.** A fee deducted from positive net cash flow before it enters
the waterfall tier distribution. Compensates the asset manager for ongoing
oversight.

**Calculation.**
```
if available_cash > 0 and am_fee_pct > 0:
    am_fee = available_cash × am_fee_pct / 100
    available_cash = available_cash − am_fee
```

**Engine source.** `OperationalInputs.asset_mgmt_fee_pct` is the input;
`compute_waterfall` (`app/engines/waterfall.py`) applies the deduction.

**Notes / edge cases.** Pre-distribution placement makes the AM fee senior to
all investor distributions, consistent with how AM fees work in real fund
structures.

### Debt Service [investor, lender, app]

**Definition.** Annual cash payment to all debt modules — interest plus
amortization (or interest only during construction / pre-stabilization).

**Calculation.**
```
debt_service_annual = Σ debt_service_monthly_per_loan × 12
```

**Engine source.** `CashFlow.debt_service` (per project, per month). The
investor export aggregates to annual buckets for the Cash Flow sheet
(`r_uw_cf_debt_service`, `r_p<n>_cf_debt_service`).

**Notes / edge cases.** Construction-phase debt service uses the loan's
construction carry rate; operations-phase uses P&I or interest-only per
the carry config. Bridge → perm refi events show up as separate
**Capital Events** lines, not in Debt Service.

### Capital Events [investor, app]

**Definition.** Per-period capital cash flows that aren't operating: the
acquisition outflow at close, exit proceeds at sale, refi takeout
proceeds, prepay penalties, and equity calls / refi shortfalls.

**Calculation.**
```
capital_events_period = Σ CashFlowLineItem.net_amount
                          where label.startswith("Acquisition" | "Sale" |
                                                 "Refi —" | "Prepay" | "Exit")
```

**Engine source.** `CashFlowLineItem` rows tagged with the category
prefixes above; the investor export separates them from operating flows
on the Cash Flow sheet so the LP sees one-time events distinctly.

**Notes / edge cases.** Y0 typically holds the acquisition outflow; the
exit-year period holds sale proceeds net of selling costs. Multi-project
deals can have acquisition outflows in different periods (anchor-driven
date resolution).

### Cumulative Cash Flow [investor, app]

**Definition.** Running total of operating + capital cash flows from
period 0 through the current period — the LP's "what's the project
worth in cumulative dollars to me right now?" view.

**Calculation.**
```
cumulative[t] = cumulative[t-1] + levered_cf[t] + capital_events[t]
cumulative[0] = levered_cf[0] + capital_events[0]
```

**Engine source.** Computed inline by the investor export from the
per-project `CashFlow.net_cash_flow` series + `CashFlowLineItem` capital
events. `CashFlow.cumulative_cash_flow` carries the engine's own running
total but resets at first stabilized month per the cash-balance seeding
invariant (§6.3), so the export computes a separate non-resetting
cumulative for the investor view.

**Notes / edge cases.** The engine's `cumulative_cash_flow` is a *cash
balance* (with reserves seeded) used for solvency tracking; the export's
**Cumulative Cash Flow** is a *return-tracking* sum used for IRR/EM
intuition. Both are valid views on the same data.

### GP Promote [investor, app]

**Definition.** Total GP profit-share dollars from the catch-up and
residual waterfall tiers — the GP's compensation for outperformance
above the LP's preferred return / hurdle.

**Calculation.**
```
gp_promote_dollars = Σ WaterfallResult.cash_distributed
                       where tier.tier_type in ("catch_up", "residual")
```

**Engine source.** `WaterfallResult` rows tagged with `catch_up` or
`residual` tier types via `WaterfallTier.tier_type`.

**Notes / edge cases.** Pure catch-up dollars (the GP catching up to
its target share *after* the LP's pref) and pure residual promote (the
GP's share of the upside above the final hurdle) both count as "promote"
from the LP's perspective — the LP cares about total fees out, not their
tier-by-tier breakdown.

### Hold Period [investor, lender, app]

**Definition.** Number of months from acquisition close to exit/divestment.
Drives the cash flow horizon, the levered IRR base, and the year axes on the
investor export.

**Calculation.**
```
hold_months = sum(phase.months for phase in phases if phase.period_type != exit)
```

**Engine source (refactor 2026-04-29).** Stabilized phase length comes from
`_resolve_horizon_months(capital_modules, orm_milestones)` in
`app/engines/cashflow.py`, then `_apply_milestone_phase_overrides` resizes
in calendar months when both `stabilized_start` and `exit_date` resolve
from the milestone trigger chain.

Resolver order:

1. Exit (`divestment`) milestone with resolvable date → override path resizes
   stabilized to `_calendar_month_count(stabilized_start, exit_date)`.
2. Else permanent-debt modules present → `MAX(perm_debt.source.hold_term_years) × 12`.
3. Else `operation_stabilized` milestone present → `duration_days // 30`.
4. Else fallback `60` months.

The deprecated `OperationalInputs.hold_period_years` column was dropped in
alembic 0060. Per-perm-debt `CapitalModule.source.hold_term_years` is the
single source of truth for loan-side hold; the divestment milestone date
overrides it for deal-side horizon when set.

**Notes / edge cases.** In multi-project deals, the scenario hold period is
the longest project's hold (so all projects' cash flows are captured).
Multi-perm-debt deals with mismatched `hold_term_years` take MAX for
horizon; per-loan early balloon at `min(hold_term × 12, horizon)` for
shorter loans is a future enhancement (currently each loan amortizes
through the full horizon unless its `exit_terms.vehicle` points at a
specific takeout source).

### 7.1 Module stack and tiers

**Capital modules** (`CapitalModule`) define the stack: debt and equity lines with a `stack_position` (0 = senior, higher = junior) and a `funder_type` (`permanent_debt`, `construction_loan`, `common_equity`, etc.).

**Waterfall tiers** (`WaterfallTier`) define the distribution order. Each tier has:
- `priority`: execution order (1 = first)
- `tier_type`: one of `debt_service`, `pref_return`, `return_of_equity`, `catch_up`, `irr_hurdle_split`, `deferred_developer_fee`, `residual`
- `lp_split_pct`, `gp_split_pct`: split ratios (for splittable tiers)
- `irr_hurdle_pct`: hurdle rate (for `irr_hurdle_split`)
- `capital_module_id`: optional link to a specific module

### 7.2 Asset management fee (pre-distribution deduction)

When `OperationalInputs.asset_mgmt_fee_pct` is set (> 0), the AM fee is deducted from positive net cash flow **before** it enters the waterfall tier distribution:

```
if available_cash > 0 and am_fee_pct > 0:
    am_fee = available_cash × am_fee_pct / 100
    available_cash = available_cash − am_fee
```

**Why pre-distribution?** The AM fee compensates the asset manager (typically the GP/sponsor's management entity) for ongoing oversight. It's an operational cost of the partnership, not a profit split. Deducting it before the waterfall ensures it's senior to all investor distributions — consistent with how AM fees work in real fund structures.

### 7.3 Capital calls (pre-distribution)

When `net_cash_flow < 0` in any period, the waterfall allocates capital calls in stack-position order:

```python
if net_cash < ZERO:
    capital_calls = _allocate_capital_calls(-net_cash, phase_name, module_states)
    for module_id, amount in capital_calls.items():
        if _is_gp_equity_module(state.module):
            _append_period_cashflow(gp_cashflows, cash_flow.period, -amount)
        elif _is_equity_module(state.module):
            _append_period_cashflows(lp_cashflows, cash_flow.period, -amount)
```

**Plain English.** Negative periods (usually construction/lease-up) are funded first by drawing debt up to commitments, then by calling equity from the lowest-priority capital (GP first if `_is_gp_equity_module`, then LP).

### 7.3 Distribution tiers (positive cash flow)

In each period with positive cash, the engine iterates through waterfall tiers in priority order, allocating until cash is exhausted.

#### Tier: `debt_service`
Pays accrued interest first, then principal at exit:
```
due = accrued_interest_due + (outstanding_principal if exit and full_payoff else 0)
amount = min(remaining_cash, due)
```

#### Tier: `pref_return`
Pays accrued preferred return on equity modules up to the cap:
```
amount = min(remaining_cash, accrued_pref_due)
```
Pref typically accrues at a fixed annual rate on outstanding contributed capital.

#### Tier: `return_of_equity`
Returns original contributions before any profit split:
```
amount = min(remaining_cash, outstanding_principal)
```

#### Tier: `catch_up`
Allows GP to "catch up" to its target share after LP pref has been paid:
```
gp_target = (gp_split / (1 − gp_split)) × total_LP_distributions_to_date
gp_shortfall = max(gp_target − total_GP_distributions_to_date, 0)
gp_amount = min(available_cash, gp_shortfall)
lp_amount = available_cash − gp_amount
```

**Plain English.** If the split is 80/20 LP/GP and LP has received $80k pref while GP has received nothing, GP's target is `(20/80) × 80k = $20k`. Catch-up tier sends up to $20k to GP before the normal split resumes.

#### Tier: `irr_hurdle_split`
LP gets everything until its IRR reaches the hurdle; above the hurdle, cash splits by tier ratios:
```
lp_irr = compute_xirr(lp_cashflows)
if lp_irr < hurdle_pct:
    all_to_lp
else:
    lp_amount = cash × lp_split
    gp_amount = cash × gp_split
```

**Why use XIRR (not IRR)?** Because our periods are monthly but distributions can happen at any period. XIRR handles irregular-date cash flows; IRR assumes equal periods.

#### Tier: `residual`
Whatever remains after all earlier tiers — split by tier ratios. This is "the promote above the final hurdle".

### 7.4 Profit metrics

### LP IRR [investor, app]

**Definition.** Internal rate of return on the LP cash flow stream.

**Calculation.** Solve for `r` such that `Σ CF_LP_i / (1 + r)^((t_i − t_0) / 365) = 0`,
where each `CF_LP_i` is the LP's net of contributions and distributions in
period i and `t_i` is the date of that period.

**Engine source.** `_compute_xirr_fraction` in `app/engines/waterfall.py`,
materialized to `OperationalOutputs.lp_irr`; used as fallback in the Excel formula.

**Excel export.** Named cell `s_lp_irr` on the Investor Returns sheet.
Formula-driven (Phase 5g): `=IFERROR(XIRR(r_returns_lp_cf,r_returns_cf_dates), {engine_fallback})`.
`r_returns_lp_cf` is the annual LP cash flow series: Y0 = −committed LP equity,
Y1..YN = waterfall distributions bucketed by year (`period // 12 + 1`).
`r_returns_cf_dates` is a shared annual date series anchored at `DEFAULT_IRR_BASE_YEAR` (2020):
Y0 = 2020-01-01, Y1 = 2021-01-01, …; shared by LP and GP XIRR calls.

**Notes / edge cases.** Annual CF buckets with equal-annual date spacing make XIRR
numerically identical to IRR() but semantically correct — allows future substitution
of real deal dates without formula changes. When the CF series has no sign change
(e.g. no equity configured), XIRR returns `#NUM!` and IFERROR substitutes the
engine scalar.

### GP IRR [investor, app]

**Definition.** IRR on the GP cash flow stream — same mechanic as LP IRR, GP side.

**Calculation.** XIRR over GP capital calls and distributions (including
promote tier proceeds).

**Engine source.** `_compute_xirr_fraction` in `app/engines/waterfall.py`,
materialized to `OperationalOutputs.gp_irr`; used as fallback in the Excel formula.

**Excel export.** Named cell `s_gp_irr` on the Investor Returns sheet.
Formula-driven (Phase 5g): `=IFERROR(XIRR(r_returns_gp_cf,r_returns_cf_dates), {engine_fallback})`.

**Notes / edge cases.** GP IRR usually exceeds LP IRR thanks to the promote;
the spread quantifies the deal's promote economics.

#### Period→date mapping

```python
def _compute_xirr_fraction(period_cashflows: dict[int, Decimal]) -> Decimal | None:
    ordered = sorted(period_cashflows.items())
    values = [float(amount) for _, amount in ordered if amount != 0]
    dates = [_period_to_date(period) for period, amount in ordered if amount != 0]
    return pyxirr.xirr(dates, values)
```

**Period → date mapping:**
```python
def _period_to_date(period: int) -> date:
    year = 2020 + (period // 12)    # DEFAULT_IRR_BASE_YEAR
    month = (period % 12) + 1
    return date(year, month, 1)
```

**Formula.** IRR solves for the rate `r` such that:
> `Σ (CF_i / (1+r)^((t_i − t_0) / 365)) = 0`

Where `CF_i` are individual cash flows (negative = contribution, positive = distribution) and `t_i` are the month-1 dates of each period.

**Why 2020 as base year?** It's arbitrary — XIRR only cares about the date differences between flows, not their absolute values. 2020 is a round number inside the pyxirr-supported range.

### LP Distributions Total [investor, app]

**Definition.** Total cash distributed to LP investors across all waterfall tiers.

**Calculation.** Sum of LP-share amounts across all configured waterfall tiers:
```
lp_distributions_total = Σ (tier_distributed × lp_split_pct / 100)  for each tier
```

**Excel export.** Named cell `s_lp_distributions_total` on the Investor Returns sheet.
Formula-driven: `=IFERROR(IFERROR(s_waterfall_tier_1_lp_amt,0)+…+IFERROR(s_waterfall_tier_7_lp_amt,0), {engine_fallback})`.
Editing Assumptions Block D LP split inputs and pressing F9 reflows this total without re-running the engine.

**Engine source.** Computed from `WaterfallResult.cash_distributed` × `WaterfallTier.lp_split_pct` for each tier.

### GP Distributions Total [investor, app]

**Definition.** Total cash distributed to GP / sponsor across all waterfall tiers (includes pref return GP share, catch-up, residual/promote).

**Calculation.** Mirror of LP Distributions Total for the GP side:
```
gp_distributions_total = Σ (tier_distributed × gp_split_pct / 100)  for each tier
```

**Excel export.** Named cell `s_gp_distributions_total` on the Investor Returns sheet.
Formula-driven: `=IFERROR(IFERROR(s_waterfall_tier_1_gp_amt,0)+…+IFERROR(s_waterfall_tier_7_gp_amt,0), {engine_fallback})`.

**Engine source.** Same as LP Distributions Total, GP side.

### Equity Multiple (MOIC) [investor, app]

```python
equity_multiple = (total_LP_positive + total_GP_positive) / (total_LP_contributed + total_GP_contributed)
```

**Plain English.** Total dollars out divided by total dollars in, across LP and GP combined. A value of 2.0× means investors doubled their money.

**Why combined LP + GP?** This is the **project-level** equity multiple. Separate LP and GP multiples are also computed but are not the headline metric.

### Weighted Equity Multiple [investor, app]

**Definition.** Time-value-adjusted equity multiple at the investor's hurdle rate: (equity invested + NPV of distributions) ÷ equity invested. A 2.0× WEM means distributions are worth 2× equity in present-value terms at the hurdle rate.

**Calculation.**
```
npv = Σ (cash_distributed_t / (1 + r)^(t/12)) − equity_required   # t in months
weighted_em = (equity_required + npv) / equity_required
```

**Engine source.** `_weighted_em_calc` + `_npv_levered` in `app/exporters/investor_export.py`. Suppressed when `equity_required < $1` (all-debt deals).

### DCF NPV [investor, app]

**Definition.** Net Present Value of levered equity cash flows discounted at the investor's hurdle rate, less equity invested. Positive = IRR exceeds hurdle; zero = exactly at hurdle; negative = below hurdle.

**Calculation.**
```
pv_distributions = Σ (cash_distributed_t / (1 + r)^(t/12))   # t in months, LP+GP equity tiers only
dcf_npv = pv_distributions − equity_required
```

**Engine source.** `_npv_levered` in `app/exporters/investor_export.py`.

### Cash-on-Cash Year 1 [investor, app]

```python
year_one_distributions = Σ positive cash flows (LP + GP) in periods 0–11
total_contributed = Σ all capital calls (LP + GP)
cash_on_cash_year_1_pct = (year_one_distributions / total_contributed) × 100
```

**Plain English.** "If I put in $1M, how much cash did I receive in year 1 as a percentage of what I put in?" — a standard first-year yield metric that's easy to explain to investors.

**Why "periods 0–11" and not "the year after stabilization"?** By convention, "year 1" means the first 12 months from deal close. If the deal is still in construction during year 1, cash-on-cash will be 0% or negative. That is the correct, honest number — the user should interpret it in context.

**LP / GP party-scoped variants (Phase 5f).** Named cells `s_lp_coc_y1` and `s_gp_coc_y1` on the Investor Returns sheet compute CoC for each party separately:
- `s_lp_coc_y1 = =IFERROR(s_returns_lp_y1 / s_committed_lp_equity, {fallback})`
- `s_gp_coc_y1 = =IFERROR(s_returns_gp_y1 / s_committed_gp_equity, {fallback})`

`s_returns_lp_y1` is the LP-side Y1 cash flow from the LP CF series row (sum of waterfall distributions to LP modules in periods 0–11). These cells alias to the "Cash-on-Cash Year 1" doc entry.

#### Debt yield (already tagged above)

The debt-yield definition lives in the §7 prelude as a tagged metric header
(`Debt Yield [lender, app]`). Repeating context here for the in-flow read:
debt yield equals stabilized NOI divided by total non-bridge debt balance.
See the tagged entry above for the full definition.

### Loss-to-Lease [investor, app]

Tracked on `UnitMix` rows via `market_rent_per_unit` and `in_place_rent_per_unit`:

```
loss_to_lease_pct = (market_rent - in_place_rent) / market_rent × 100
```

A positive LTL indicates below-market rents — the primary value-add opportunity in multifamily acquisitions. Three of five benchmark CRE models (A.CRE Acquisition, PropRise, A Simple Model) track LTL as a first-class metric. Exported in the JSON payload via `unit_mix` and available for investor-facing reports.

### 7.5 Debt service in the waterfall — cashflow engine is authoritative

The cashflow engine computes debt service using closed-form IO/P&I formulas and writes the authoritative `debt_service`, `net_cash_flow`, and `cumulative_cash_flow` columns on every `CashFlow` row. **The waterfall engine does not overwrite these values.**

`_apply_levered_metrics` builds `levered_cashflows` directly from the cashflow engine's `net_cash_flow` for use in levered IRR:

```python
for cash_flow in _default_cashflows:
    levered_cashflows[cash_flow.period] = _to_decimal(cash_flow.net_cash_flow)
```

DSCR is then computed from the `_default_cashflows` rows using the cashflow engine's `debt_service` values (via `_compute_dscr`), and written to `OperationalOutputs.dscr`.

**Why not use WaterfallResult.cash_distributed for the debt_service tier?** The waterfall distributes from **post-DS** `net_cash_flow` as `available_cash`. This means the `debt_service` tier receives only the residual equity slice (e.g. NOI $45,352 − DS $36,770 = $8,582/period) — not the PMT obligation. Reading `cash_distributed` from this tier and writing it back to `cash_flow.debt_service` would swap the two values (debt_service ≈ $8,582, net_cash_flow ≈ $36,770), corrupting DSCR for both single- and multi-project deals. The cashflow engine's sized PMT is the correct obligation; the waterfall respects it.

### 7.6 Levered vs unlevered project IRR

- **Unlevered project IRR**: `XIRR(TPC outflows, NOI inflows, exit proceeds)` — returns as if the deal were 100% equity. Measures asset quality.
- **Levered project IRR**: `XIRR(equity contributions, post-DS distributions, post-payoff residual)` — returns to the equity stack. Measures the deal's return after leverage.

The spread between the two is the "leverage amplification" — positive if leverage is accretive, negative if the deal is over-levered.

### Unlevered IRR [investor, app]

**Definition.** XIRR of TPC outflows, NOI inflows, and exit proceeds — the
return as if the deal were 100% equity. Measures asset quality independent
of capital structure.

**Calculation.**
```
unlevered_irr = XIRR(
  outflows = TPC capital deployments,
  inflows  = monthly NOI + exit proceeds (net of selling costs)
)
```

**Engine source.** `OperationalOutputs.unlevered_irr` (computed by the
cashflow engine per project, aggregated by `rollup_irr`).

**Notes / edge cases.** Unlevered IRR is the standard apples-to-apples metric
for comparing assets across different capital stacks.

### Levered IRR [investor, app]

**Definition.** XIRR of equity contributions and post-debt-service distributions
through exit — the return realized by the equity stack after leverage.

**Calculation.**
```
levered_irr = XIRR(
  outflows = equity capital calls,
  inflows  = post-DS distributions + post-payoff residual at exit
)
```

**Engine source.** `OperationalOutputs.levered_irr` (waterfall engine writes
the authoritative value via `_apply_levered_metrics`).

**Notes / edge cases.** Levered IRR > unlevered IRR when leverage is
accretive; reversed when the deal is over-levered. The spread is what the
investor is paying the GP to engineer.

### Levered Cash Flow [investor, app]

**Definition.** Net cash flow to the equity stack each period after debt
service.

**Calculation.**
```
levered_cf_period = NOI − debt_service − capital_outflows + capital_inflows
```

**Engine source.** `CashFlow.net_cash_flow` (per project; rollup sums across
projects for scenario-wide display).

**Notes / edge cases.** Negative levered CF triggers capital calls in the
waterfall. Cumulative levered CF resets to the operating reserve at first
stabilized month — see §6.3.

### Unlevered Cash Flow [investor, app]

**Definition.** Net cash flow assuming no debt — operating cash flow plus
capital events, minus capital outflows.

**Calculation.**
```
unlevered_cf_period = NOI − capital_outflows + capital_inflows
```

**Engine source.** Computed inline by the investor export sheet builder from
`CashFlow.noi`, `CashFlowLineItem` capital events.

**Notes / edge cases.** Subtracting debt service from unlevered CF gives
levered CF — the two columns appear side-by-side on the investor cash flow
sheet so the LP can see the leverage spread per period.

### 7.7 Calculation Status diagnostic (3-factor model)

The Calculation Status pill in the builder topbar surfaces the health of the model via three factors. Any factor in `warn` or `fail` state marks the overall as `warn` (yellow); all `ok`/`na` = `ok` (green).

**Factor 1: Sources = Uses**
```
gap = capital_total − uses_total
```
- `|gap| < $1` → `ok` "Sources = Uses"
- `gap > 0` → `warn` "Surplus $X" (extra capital not needed)
- `gap < 0` → `fail` "Gap $X" (Uses exceed Sources)

**Factor 2: DSCR**
```
dscr = noi_stabilized / (operation_debt_monthly × 12)
```
- `dscr ≥ source.dscr_min` (first perm-debt module; fallback `1.20`) → `ok` with headroom amount
- `dscr < source.dscr_min` → `fail` with shortfall amount

**Factor 3: LTV**
```
property_value = noi_stabilized / (exit_cap_rate_pct / 100)
actual_ltv_pct = total_non_bridge_debt / property_value × 100
```
- Computed regardless of sizing mode (always shown as informational)
- When `debt_sizing_mode == "dual_constraint"`: green/red status based on binding constraint (red if LTV binds AND gap exists)
- When any other sizing mode: grey `na` status with the computed LTV %

**Pill label (center-top of builder):**
- All `ok`: "✓ Calculation Valid"
- Single failing factor: specific label (e.g., "⚠ -$478,284 Sources Gap", "⚠ 1.14× DSCR — Too Low", "⚠ 72.3% LTV — Too High")
- Multiple failures: "⚠ N issues"

Click opens a modal with per-factor details, current/target values, and actionable explanation text.

**Endpoints:**
- `GET /ui/models/{id}/calc-status` — pill HTML
- `GET /ui/models/{id}/calc-status/modal` — modal body HTML

The pill replaces the legacy sidebar "Sources = Uses" banner (removed April 18 2026).

---

## 8. Key constants and defaults (quick reference)

| Constant | Value | Where it lives | What it controls |
|---|---|---|---|
| `MONEY_PLACES` | `Decimal("0.000001")` | cashflow.py | 6-decimal rounding for all cash math |
| `DEFAULT_IRR_BASE_YEAR` | `2020` | waterfall.py | Period → date conversion origin for XIRR |
| `PLACEHOLDER_DSCR` | `Decimal("1.25")` | cashflow.py | Fallback if `CapitalModule.source.dscr_min` not set on perm-debt module |
| `_LEASE_UP_INCOME_FACTOR` | `1/3` | cashflow.py | Phantom CF avg income during lease-up |
| `operation_reserve_months` | `6` (default) | OperationalInputs | Reserve horizon for gap-fill sizing |
| `initial_occupancy_pct` | `0` (default when NULL, as of 2026-06-03) | OperationalInputs | Starting point of lease-up ramp. Wizard slider supplies an explicit value on new deals. |
| `stabilized_occupancy_pct` | `95` (default) | IncomeStream | Ending point of lease-up ramp |
| `expense_growth_rate_pct_annual` | `3` (default) | OperationalInputs | Annual OpEx escalation |
| `noi_escalation_rate_pct` | `3` (default) | OperationalInputs | NOI-mode escalation |
| `bad_debt_pct` | `0` (default) | IncomeStream | % of GPR lost to bad debt |
| `concessions_pct` | `0` (default) | IncomeStream | % of GPR lost to concessions |
| `renovation_absorption_rate` | `NULL` (default) | IncomeStream | Ramp fraction for reno premium phase-in |
| `prepay_penalty_pct` | `NULL` (default) | CapitalSourceSchema (JSONB) | % of balloon balance at payoff |
| `refi_cap_rate_pct` | `NULL` (default) | CapitalSourceSchema (JSONB) | Cap rate override for refi LTV sizing |
| `asset_mgmt_fee_pct` | `NULL` (default) | OperationalInputs | AM fee deducted pre-waterfall |
| `debt_yield_pct` | computed | OperationalOutputs | NOI / total debt balance × 100 |
| `sensitivity_matrix` | computed (JSON) | OperationalOutputs | 5×5 grid storage for investor export |
| `lease_up_curve` | `NULL` → "linear" | OperationalInputs | "linear" or "s_curve" ramp shape |
| `lease_up_curve_steepness` | `NULL` → 5 | OperationalInputs | S-curve steepness (1=flat, 10=steep) |
| `market_rent_per_unit` | `NULL` | UnitMix | Market rent for loss-to-lease calculation |
| `in_place_rent_per_unit` | `NULL` | UnitMix | Current lease rent for LTL |
| `renovation_capture_schedule` | `NULL` | IncomeStream | Discrete year-by-year capture rates (JSON, engine only) |
| `catchup_target_rent` | `NULL` | IncomeStream | Market rent target for LTL catchup escalation |
| `LTL_CATCHUP_CAP_PCT` | `10` | cashflow.py constant | Max annual rent increase % during LTL catchup |
| `unit_strategy` | `NULL` | UnitMix | "base_escalation", "ltl_catchup", or "value_add_renovation" |
| `post_reno_rent_per_unit` | `NULL` | UnitMix | Monthly rent after renovation (value-add strategy) |
| `beds` | `NULL` | UnitMix | Bedrooms (0–5+, whole numbers) |
| `baths` | `NULL` | UnitMix | Baths (0–3.5+, 0.5 increments) |
| `MAX_ITERATIONS` | `5` | models.py compute endpoint | Fix-point iteration cap for DSCR convergence |
| `DSCR_CONVERGENCE_TOLERANCE` | `0.005` | models.py compute endpoint | DSCR stability threshold between iterations (half a bp) |
| `first_stab_period` | computed | compute_cash_flows loop | Month index of first stabilized phase; anchor for NOI-mode escalation |

---

## 9. Why we made the choices we made — summary

1. **Exact avg-draw formula (`rate/12 × (N+1)/2`) over industry 50% heuristic** for Interest Reserve sizing. We model monthly draws, so we can compute the exact factor rather than the large-N limit. On short construction timelines this matters.

2. **Four distinct carry types** (True IO, Interest Reserve, Capitalized Interest, P&I) instead of three or two. Phase 1 rewrite split True IO from Interest Reserve because they produce different principals for the same base cost. Matches Argus / REFM / FDIC handbook conventions.

3. **`max(OpEx, DS)` for operating reserve** in revenue_opex mode. Both obligations are ongoing; the reserve must cover the larger one. NOI mode sizes on DS only because OpEx isn't broken out.

4. **`1/3` lease-up income factor** (not `1/2`). The derivation in §2.6 shows that linear revenue ramps combined with sticky fixed costs produce a 33.3% average, not 50%. The difference is material (~$63k on a 9-month lease-up at $500k NOI).

5. **Closing costs folded into perm divisor** (not iterated). `P × (1 − 0.5%) = TPC → P = TPC / 0.995` is exact in one pass. Iterative convergence would work but is fragile and ugly.

6. **Closing costs excluded from bridge loan sizing via `_cc_labels`**. A construction loan should not cover its own origination fee — the fee lives in `pre_construction`, the same phase that sizes the pre-dev loan. Without the exclusion, pre-dev loan would double-count. Perm gap-fill covers all closing costs.

7. **Cashflow engine is authoritative for `debt_service`, `net_cash_flow`, and `cumulative_cash_flow`.** The waterfall engine does not overwrite these columns. The waterfall distributes from post-DS `net_cash_flow` as `available_cash`, so `WaterfallResult.cash_distributed` for the `debt_service` tier is the residual NCF allocation — not the PMT obligation. Overwriting `cash_flow.debt_service` with this value would swap the two columns and corrupt DSCR. `_apply_levered_metrics` builds `levered_cashflows` from the cashflow engine's `net_cash_flow` and computes DSCR from the cashflow engine's `debt_service` values.

8. **Cumulative cash flow resets to operating reserve at first stabilized month**. This is the invariant the entire gap-fill formula is designed to satisfy. Without it, you couldn't prove that Sources = Uses after the cash flow loop runs. With it, the reserve is guaranteed to exist at stabilization regardless of what happens in lease-up.

9. **6-decimal Decimal precision throughout**. Eliminates rounding drift across 60+ periods of compounding math. Sources = Uses must balance to the penny, not "close enough".

10. **Always-recompute vs user-override sentinels**. Operating Reserve, Capitalized Interest, Lease-Up Reserve are always recomputed from current debt (pure derivation). Closing costs respect `amount > 0` as a user override (allows real deal terms to override market defaults). This split matches how users actually think about these numbers.

11. **MIN(LTV, DSCR, gap-fill) three-way constraint** (not just MIN(LTV, DSCR)). Gap-fill acts as a ceiling: there's no point borrowing more than the project needs, even if the lender would fund it. This prevents deals from showing negative equity (sources > uses) when LTV/DSCR constraints are loose.

12. **Refi cap rate defaults to going-in cap, not exit cap**. Conservative: assumes no cap rate compression from value-add. The projected NOI at stabilization already reflects vacancy, bad debt, concessions, and lease-up — so the cap rate applied to it is purely about market pricing of the income stream, not operational risk discounting. Override via `refi_cap_rate_pct` for scenarios modeling cap compression.

13. **Bad debt and concessions as separate named fields** (not bundled into vacancy). The math is equivalent (all are % deductions from GPR), but separating them matches the standard CRE pro forma format and enables HelloData/CoStar data feeds that provide these as distinct fields.

14. **American-style waterfall only** (no European toggle). American (period-by-period distribution) is the standard for US multifamily syndications. European (return-all-capital-plus-pref-before-any-promote) can be modeled by arranging `return_of_equity` and `pref_return` tiers in the correct priority order — no separate engine path needed.

15. **Renovation absorption as a per-stream attribute** (not a global deal setting). Different income streams may have different absorption profiles — e.g., residential rent premiums phase in with unit turns, but parking income may stabilize immediately. Per-stream gives the user control without global assumptions.

16. **S-curve lease-up as opt-in** (linear default). Linear is transparent, conservative, and produces verifiable results. S-curve is more realistic for large projects but adds a steepness parameter that most users won't calibrate. Default to the simpler model; power users can switch via `lease_up_curve = "s_curve"`. Modeled after Adventures in CRE Development Model which offers a similar toggle.

17. **Debt yield as a standard output metric** alongside DSCR. Three of five benchmark models expose debt yield. Lenders increasingly use it as a rate-independent coverage measure. Computed as `NOI / total_debt_balance` — no new inputs required, just a new output.

18. **Loss-to-lease on UnitMix** (not IncomeStream). LTL is a property characteristic (market vs. in-place rent), not an income stream attribute. It lives on UnitMix because that's where unit-level rent data belongs. The value-add thesis is literally "buy at in-place, renovate to market."

19. **Discrete capture schedule as alternative to continuous ramp**. PropRise uses 0%/50%/100% year-by-year steps. This is simpler to explain to investors than a continuous fraction. Both options available per-stream: `renovation_capture_schedule` (discrete) overrides `renovation_absorption_rate` (continuous) when set.

20. **NOI-mode escalation anchored at first stabilized month** (April 18 2026). The user-entered `noi_stabilized_input` means "NOI at year 1 of stabilization" (underwriting convention), not "NOI at deal close". Previously escalation ran from deal month 0, causing DSCR drift in `dscr_capped` / `dual_constraint` sizing. Anchor fix: `esc_period = max(0, period − first_stab_period)`. First stabilized month = raw input (no escalation applied yet).

21. **Fix-point iteration for sizing convergence** (April 18 2026). DSCR-bound sizing requires knowing the "true" NOI, but the first compute pass can only use an estimate. Each subsequent call reads the previous OperationalOutputs.noi_stabilized, so re-running converges in 2 passes. The `/compute` endpoint loops up to 5x with a 0.005× DSCR tolerance. `gap_fill` mode breaks after one pass.

22. **Deal type labels renamed for business clarity** (April 18 2026). Display labels updated throughout the UI:
    - `acquisition` → "Acquisition" (was "Minor Renovation"). Construction milestone removed from the default preset — this strategy is pure hold/stabilize with LTL catchup or base escalation on unrenovated units.
    - `value_add` → "Value-Add" (was "Major Renovation"). Used for unit renovations with measurable rent uplift.
    - `conversion` → "Conversion" (was "Acquisition — Conversion"). Change-of-use projects.
    - `new_construction` unchanged.
    Enum values kept for DB compatibility; only display strings changed.

23. **Calculation Status pill over sidebar balance bar** (April 18 2026). A center-top pill replaces the legacy sidebar "Sources = Uses" banner. Surfaces three factors (S=U gap, DSCR vs. minimum, LTV vs. binding constraint) with per-factor details in a modal. Single-issue label shows the specific value ("⚠ -$478,284 Sources Gap" rather than "⚠ 1 issue") for immediate diagnostic context.

24. **Legacy `avg_monthly_rent` removed; beds/baths added** (April 18 2026). `avg_monthly_rent` duplicated `in_place_rent_per_unit` semantically. Beds (0–5+, whole numbers) and baths (0–3.5+, 0.5 increments) are now first-class numeric variables so comp-data ingestion can populate them directly. Migration 0046 drops the legacy column.

---

## 10. Sources (market data for closing cost defaults)

- [How Much Are Commercial Property Closing Costs? — commloan](https://www.commloan.com/research/commercial-property-closing-costs/)
- [Commercial Property Closing Costs: What to Know — Finance Lobby](https://financelobby.com/cre-insights/commercial-property-closing-costs-what-to-know/)
- [Bridge Loan Costs in 2025 — Hurst Lending](https://hurstlending.com/cost-of-a-bridge-loan/)
- [Phase I ESA Costs & Best Practices for 2025 — Aegis Environmental](https://aegisenvironmentalinc.com/phase-i-environmental-site-assessment-costs/)
- [Ins and Outs of Construction Loan Closing Costs — FasterCapital](https://fastercapital.com/content/Ins-and-Outs-of-Construction-Loan-Closing-Costs.html)
- [Construction Loan Closing Costs — mrrate](https://mrrate.com/guide/construction-loan-closing-costs-on-fees/)
- [Understanding Commercial Closing Costs — Rochford Law](https://info.rochfordlawyers.com/resources/understanding-commercial-closing-costs)
- FDIC Comptroller's Handbook — Commercial Real Estate Lending (for carry type conventions)
- Argus Enterprise, REFM documentation (for industry practice on IR, CI, True IO distinctions)

---

*Document current as of April 18, 2026. Recent updates: NOI escalation anchor + fix-point iteration (§4.6–4.7), Calculation Status diagnostic (§7.7), UnitMix bed/bath + strategy (§4.8), deal type rename, constants table. Prior: HelloData model parity (§2.8–2.10, §4.5, §6.4–6.5, §7.2 AM fee). When changing any formula, update the corresponding section and reference the commit hash.*

---

## Appendix A: Per-Loan Active-Window Months (April 2026)

### A.1 Why per-loan windowing replaced `constr_months_total`

Prior to April 2026, every bridge loan used the same global `constr_months_total` — the sum of all construction-type phase months. This was wrong for multi-debt deals where loans have different active periods. A pre-development loan active from close to construction should only count pre-construction months, not the full construction duration.

### A.2 Phase rank system

Each phase has a numeric rank. A loan's active window is `[start_rank, end_rank)` — half-open, end-exclusive.

```python
_PERIOD_TYPE_RANK = {
    PeriodType.acquisition:      0,
    PeriodType.hold:             1,
    PeriodType.pre_construction: 2,
    PeriodType.construction:     3,  # also minor_renovation, major_renovation, conversion
    PeriodType.lease_up:         4,
    PeriodType.stabilized:       5,
    PeriodType.exit:             6,
}

_APS_TO_RANK = {
    "acquisition": 0, "close": 0,
    "pre_construction": 2,
    "construction": 3,
    "lease_up": 4, "operation_lease_up": 4,
    "stabilized": 5, "operation_stabilized": 5,
    "exit": 6, "divestment": 6,
}
```

### A.3 `_loan_pre_op_months(module)` function

```python
def _loan_pre_op_months(module) -> int:
    start_rank = _APS_TO_RANK.get(module.active_phase_start, 0)
    end_rank   = _APS_TO_RANK.get(module.active_phase_end, 99)
    return sum(
        p.months for p in phases
        if p.period_type in _CONSTRUCTION_PERIOD_TYPES
        and start_rank <= _PERIOD_TYPE_RANK.get(p.period_type, 99) < end_rank
    )
```

**End-exclusive semantics.** `active_phase_end = "operation_stabilized"` (rank 5) means the loan is active for all phases with rank < 5. The loan is NOT active during stabilized itself — it is taken out at the START of stabilized. This matches CRE convention: a construction loan is retired when the project stabilizes.

**Example.** A construction loan with `active_phase_start = "pre_construction"` (rank 2) and `active_phase_end = "lease_up"` (rank 4):
- Counts pre_construction (rank 2) + construction (rank 3) = both included
- Does NOT count lease_up (rank 4) — end-exclusive
- If pre_construction = 3 months, construction = 12 months → N = 15

### A.4 Impact on carry formulas

All three bridge loan branches (pre-dev, acquisition, construction) call `_n = _loan_pre_op_months(_m)` instead of the global `constr_months_total`. The carry formulas themselves are unchanged — only the input `N` is now per-loan.

---

## Appendix B: Milestone Trigger Chains (April 2026)

### B.1 How phase durations reach the engine

The cashflow engine derives phase months from milestone dates. Milestones form a **trigger chain**: each non-anchor milestone has a `trigger_milestone_id` pointing to the previous milestone, with `trigger_offset_days = 0`. The chain is:

```
close (anchor, fixed date) → pre_development → construction → lease_up → stabilized → divestment
```

`computed_start(milestone_map)` walks the chain: `start = trigger_milestone.computed_start() + trigger_milestone.duration_days + offset_days`.

### B.2 Fallback behavior

If a milestone has no `trigger_milestone_id`, `computed_start()` returns `None`. The engine then falls back to `OperationalInputs.*_months` scalars. If those are also NULL (common for wizard-created deals), the phase defaults to 1 month.

This fallback produces degenerate carry math — e.g., a 12-month construction project computing with N=1. Deals created before the trigger-chain fix (commit `5d5caf4`) may need a backfill script.

### B.3 Timeline wizard two-pass creation

The timeline wizard creates milestones in two passes:
1. **Pass 1:** Create all milestones with durations + target_date on the anchor
2. **Pass 2:** Wire `trigger_milestone_id` so `computed_start()` resolves for every non-anchor milestone

Without Pass 2, the engine can't derive phase durations from milestones.

### B.4 Divestment as a single-day event

Divestment has `duration_days = 1` across all deal types. It represents the sale closing date — a point-in-time event, not a phase with duration. The cashflow engine uses `PhaseSpec(PeriodType.exit, 1)` for the exit phase regardless of the milestone's actual duration.

On the Gantt, divestment gets a minimum display width of 30 days for visual presence (`_GANTT_DISPLAY_MINS`).

---

## Appendix C: Multi-Phase Carry Configuration (April 2026)

### C.0 Two carry formats

Two JSONB shapes exist and serve different purposes:

| Format | Where stored | Purpose |
|---|---|---|
| `phases` array (engine format) | `CapitalModule.carry` | Consumed by cashflow engine; max 2 phases named `construction` / `operation` |
| `schedule` array (wizard format) | `SourceVehicle.carry_config` | UI template; arbitrary N phases with duration/milestone anchors; wizard pre-fills from this on vehicle select |

The wizard's "Simple (2-phase)" mode writes flat `construction_carry_type` / `operation_carry_type` keys; the engine maps these to the `phases` format internally. The wizard's "Custom Schedule" mode writes the `schedule` array to `carry_config` on the vehicle (see DATA_MODEL.md §12.6a).

### C.1 Phased carry format (engine)

A single loan can have different carry types in different phases. The `carry` JSONB column stores this as:

```json
{
  "phases": [
    {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": 7.0},
    {"name": "operation",    "carry_type": "pi",               "io_rate_pct": 6.5, "amort_term_years": 30}
  ]
}
```

The engine's `_carry_type_for_phase(carry, is_construction)` extracts the carry type for the relevant phase. The `_get_phase_carry(carry, phase_name)` function returns the full phase dict for rate lookup.

### C.2 Rate lookup precedence

For any carry calculation, the rate is resolved as:
1. `source["interest_rate_pct"]` (from the capital module's source config)
2. `carry_phase["io_rate_pct"]` (from the phase-specific carry dict)
3. `carry["io_rate_pct"]` (from the flat carry format, legacy)

### C.3 Common patterns

| Pattern | Construction carry | Operations carry | Example |
|---|---|---|---|
| True IO → P&I | `io_only` | `pi` | Typical construction + perm |
| Interest Reserve → P&I | `interest_reserve` | `pi` | Construction with reserve |
| Capitalized Interest → P&I | `capitalized_interest` | `pi` | PIK during construction |
| IO then PI (C2P) | `io_only` | `pi` | Construction-to-perm bond |

### C.4 `"accruing"` alias

The carry type `"accruing"` is normalized to `"capitalized_interest"` by `_carry_type_for_phase()` in the cashflow engine only. The waterfall engine keeps `"accruing"` distinct for side-pocket vs principal accrual treatment. User-facing UI shows "Capitalized Interest (PIK)".

---

## Appendix D: Two-Way Sensitivity (April 2026)

### D.1 What it is

A 5x5 grid of Combined Levered IRR computed by re-running the full cashflow engine across the cartesian product of two assumption axes. The default pair is **Exit Cap Rate** (rows) × **NOI / Rent Growth** (columns) — the two highest-conviction-loss variables for stabilized multifamily underwriting per the LP/IC sensitivity convention.

The grid is rendered as the **Sensitivity** sheet of the investor Excel export (between Underwriting Cash Flow and Investor Returns) and is also surfaced in the in-app Sensitivity tab via `compute_sensitivity_matrix()`.

### D.2 Engine — `compute_sensitivity_matrix`

Located at `app/engines/sensitivity_matrix.py`. Two modes:

- **`mode="first"`** (default, back-compat): mutates only the first project's `OperationalInputs`. Cell value is read from the last project's per-project summary returned by `compute_cash_flows`. Suitable for single-project scenarios and the existing UI Sensitivity tab.
- **`mode="combined"`**: mutates **every** project's `OperationalInputs` in lockstep. For `metric="project_irr_levered"` the cell value is the deal-level Combined Levered IRR computed via `rollup_irr` over the summed monthly NCF series across all projects. Required for multi-project deals where the per-project IRR doesn't reflect the LP-facing return.

Steps per axis are configurable via `step_overrides: dict[str, Decimal]`. The investor export uses:
- `noi_escalation_rate_pct` step = `1.0` (window ±200bps around base)
- `exit_cap_rate_pct` step = `0.5` (window ±100bps around base)

### D.3 Grid layout in the investor export

| Row | Content |
|---|---|
| 1 | Title: "Two-Way Sensitivity" |
| 2 | Subtitle: `<axis_y_label> × <axis_x_label> → <metric_label> (combined deal-level)` |
| 4 | Corner label (A4) + x-axis values (B4:F4) |
| 5–9 | y-axis values (A5:A9) + 5x5 IRR grid (B5:F9) |
| 11 | Base-case readout (axis values + base IRR) |
| 13+ | Notes |

The base-case cell uses the brand fog fill + hero-value font. The data range carries a red→yellow→green 3-color conditional-formatting scale (red = lowest IRR, green = highest). Failed cells (engine errors, infeasible debt sizing) appear blank rather than zero so they don't skew the gradient.

### D.4 Defined name

The 5x5 data range registers the workbook-scoped name `r_sensitivity_grid`. External tooling can `INDIRECT()` against it; the bidirectional doc validator aliases this name to the existing **Levered IRR** doc entry (the underlying metric for every cell).

### D.5 Performance

Each cell is one full `compute_cash_flows` cycle. 25 cells × ~0.2s = ~5s added to export latency. Acceptable for a synchronous LP-facing artifact; not used for Monte Carlo (10K+ runs would need Celery offload).

### D.6 Mutation safety

The engine mutates `OperationalInputs` in place during the run, then restores per-project base values from a snapshot taken before iteration begins. A final `compute_cash_flows` call re-persists the base-case `CashFlow`/`OperationalOutputs` rows so downstream rollup queries see consistent numbers. The mutation window is the duration of the export request; concurrent reads during this ~5s window may see transient values.


---

## Appendix E: Gap Adjustment Sliders + Compile/Evaluate Split (April 2026)

### D.1 Motivation

When the auto-sizer hits the DSCR floor (default 1.15) or the user's LTV cap, a Sources/Uses gap appears that the engine cannot close on its own. The user has to pick where to give: lower Purchase Price, raise Revenue assumptions, or cut OpEx — each choice has different real-world feasibility, so the model can't decide for them. The Gap Adjustment slider feature gives the user three knobs:

- **Revenue (/mo)** — adds a fixed monthly amount to gross revenue
- **OpEx (/yr)** — adds an annual amount (negative = imagined reduction) to operating expenses
- **Purchase Price** — adds an amount (negative = imagined reduction) to total Uses

Each slider materializes a **phantom line item** in the corresponding table (`IncomeStream`, `OperatingExpenseLine`, `UseLine`). The phantom row persists in the database, so the user's "what reach was needed to make this pencil" survives across sessions and tells the deal's story. Drag a slider to zero and the row stays at zero (gray, un-highlighted) — the lineage is preserved. Click "Reset all" and all three rows go to zero in one action.

### D.2 Reserved labels (single source of truth)

The three phantom rows are identified by exact-match labels, defined in `app/schemas/gap_adjustment_names.py`:

```python
REVENUE_ADJUSTMENT_LABEL          = "Gap Adjustment — Revenue"
OPEX_ADJUSTMENT_LABEL             = "Gap Adjustment — OpEx"
PURCHASE_PRICE_ADJUSTMENT_LABEL   = "Gap Adjustment — Purchase Price"
```

`is_reserved_label(label)` returns True for an exact match; comparison is case- and whitespace-sensitive. The constants are imported wherever name protection is enforced (Pydantic schemas, router handlers, the slider endpoint, the pill renderer, the panel template).

### D.3 Name protection (perimeter)

The slider feature is the only legitimate creator/mutator of phantom rows. Two enforcement layers:

- **Pydantic validators** (`app/schemas/deal.py`): `IncomeStreamCreate`/`Update`, `OperatingExpenseLineCreate`/`Update`, and `UseLineCreate`/`Update` all run `_validate_label_not_reserved` on the `label` field. Any user attempt to create a new row with a reserved label or rename an existing row to a reserved label fails with a `ValidationError`. Read schemas are unaffected — they have to deserialize phantom rows from the DB.

- **Router guards** (`app/api/routers/models.py`): the PATCH and DELETE handlers for `/income-streams/{id}`, `/expense-lines/{id}`, and `/use-lines/{id}` all call `_assert_not_phantom_row(label, kind)` before mutating. If the target row's label is reserved, the handler returns HTTP 403 with a message pointing the user at the slider drawer.

To remove an adjustment, the user drags the slider back to zero. Direct `DELETE` of phantom rows is intentionally blocked.

### D.4 Slider endpoint

`POST /api/models/{model_id}/sliders` (defined in `app/api/routers/models.py`):

```jsonc
// Request
{
  "revenue_delta_monthly": "1000",   // optional; null = leave revenue phantom alone
  "opex_delta_annual":     "-12000", // optional; negative supported
  "pp_delta":              "-50000"  // optional; negative supported
}

// Response (SliderResponse)
{
  "revenue_delta_monthly": "1000",
  "opex_delta_annual":     "-12000",
  "pp_delta":              "-50000",
  "has_any_adjustment":    true,         // drives pill yellow override
  "dscr":                  "1.235",      // post-compute
  "total_project_cost":    "1850000",
  "equity_required":       "0"
}
```

For each non-null delta, the endpoint upserts the corresponding phantom row to that absolute amount on the deal's default project. Omitted fields leave the row untouched. After the upserts, `compute_cash_flows` runs synchronously and the response carries the post-compute metrics.

The endpoint bypasses the schema validators (it writes via ORM directly) — that's the intended contract: the slider is the only path that legitimately produces reserved-label rows.

### D.5 How phantom amounts flow into the engine

Phantom rows are **structurally identical** to user-created rows of the same type. The cashflow engine doesn't special-case them:

- A `Gap Adjustment — Revenue` row is an `IncomeStream` with `amount_fixed_monthly` set. Its amount flows into `_calculate_noi_period` (cashflow.py:1470 area) and adds to monthly gross revenue across the operating phases listed in `active_in_phases` (default: lease_up, stabilized, exit).

- A `Gap Adjustment — OpEx` row is an `OperatingExpenseLine` with `annual_amount` set, possibly negative. The engine sums it directly: `operating_expenses += annual / 12` (cashflow.py:1476). A negative annual amount reduces total OpEx, which is the "imagine OpEx were $X lower" semantic.

- A `Gap Adjustment — Purchase Price` row is a `UseLine` with `amount` set, possibly negative, in the acquisition phase. The auto-sizer sums all use_lines in `_auto_size_debt_modules` (cashflow.py:1603): `total_uses += _to_decimal(ul.amount)`. A negative amount subtracts from total Uses, lowering the principal solve and reducing the Sources/Uses gap.

No ORM CHECK constraints, no Pydantic `ge=0`, no UI input minimums prevent negatives — the engine has supported negative line items all along.

### D.6 Pill yellow override

The calc-status pill (top of the model builder page) normally renders green ("✓ Calculation Valid") when Sources=Uses, DSCR≥floor, and LTV≤cap. When *any* phantom row has a nonzero amount, that green state is overridden to yellow ("⚠ Balanced w/ adjustments"):

```python
# app/api/routers/ui.py — _render_calc_status_pill_html
if status["overall"] == "ok" and has_any_adjustment:
    label = "⚠ Balanced w/ adjustments"
    cls = "warn"
elif status["overall"] == "ok":
    label = "✓ Calculation Valid"
    cls = "ok"
else:
    # real failure — keep existing warn label
    ...
```

Real failures (gap nonzero, DSCR below floor, LTV above cap) keep their existing warn label even when phantoms are nonzero — `has_any_adjustment` doesn't downgrade real failures, only converts the otherwise-green case.

The flag is computed by `_has_any_gap_adjustment(session, project_id)`, which queries the three phantom rows and returns True iff at least one has a nonzero amount.

### D.7 Compile / Evaluate engine split (foundation, partial)

The slider drawer's "drag, see DSCR move" UX wants snappy response per slider release. The current implementation runs the full `compute_cash_flows` engine on each POST — fine for now (200ms–2s perceived latency over a debounced release), but the architectural goal is to split the engine into two phases so future slider drag can be sub-100ms server-side:

- **`compile(scenario) → CompiledScenario`**: builds all structure that doesn't depend on slider inputs (timing, schedules, trigger chains, rates, terms, escalation factors, lease-up curves). Runs once per scenario.
- **`evaluate(compiled, dR, dE, dP) → EvaluationResult`**: takes the compiled structure plus three scalar deltas (revenue monthly, opex annual, PP). Returns sized loan, total uses/sources, DSCR/LTV, gap, per-period arrays. Cheap (~1ms) and pure.

The full save/export path is `evaluate(compile(scenario), 0, 0, 0)` — same code path as the slider, just with zero deltas. **No parallel implementation** — preventing two-engine drift was the explicit reason for choosing this approach over a separate fast estimator.

**Status as of this writing (April 2026):**
- ✅ Phase-plan layer extracted to `app/engines/cashflow_compile.py` (PR1 slice 1): `PhaseSpec`, `_build_phase_plan`, `_milestone_dates_from_orm`, helpers
- ✅ Per-loan windowing + Exit Vehicle pairing extracted (PR1 slice 2): `_APS_TO_RANK`, `_PERIOD_TYPE_RANK`, `_module_rank`, `_eligible_retirers`, `_resolve_vehicle`, `_resolve_active_end_rank`, `_loan_pre_op_months`
- ✅ Per-period structural helpers extracted (PR1 slice 3): `_is_stream_active`, `_is_expense_line_active`, `_stream_occupancy_pct`, `_operating_unit_count`, `_phase_is_operational`, `_growth_factor`, `_manifest_unit_count`
- ⏳ Auto-sizer arithmetic + DB writeback split (PR2): the 1,000+ line `_auto_size_debt_modules` still mixes principal-solve math with ORM mutation. Closed-form `evaluate()` and pure `persist_evaluation()` are deferred until the debounced full-engine UX proves too slow in practice.

### D.8 Snapshot harness as safety net

The compile/evaluate refactor is risky — cashflow.py drives every financial number on the platform. Byte-identical output across the refactor is enforced by the snapshot harness at `tests/engines/test_engine_snapshots.py`:

- Four scenarios cover the major engine paths: minimal NOI, single-project + auto-sized perm debt + IO carry, new-construction with capitalized-interest carry + retirement chain, multi-project rollup
- Each scenario seeds via in-memory SQLite, runs `compute_cash_flows`, serializes the full persisted state (CashFlow, CashFlowLineItem, OperationalOutputs, post-auto-size CapitalModule.source.amount) to canonical JSON
- Output is compared byte-for-byte against checked-in snapshots; `SNAPSHOT_UPDATE=1 pytest ...` regenerates when engine output is intentionally changed
- Snapshot serializer sorts in Python by stable project_idx ordinal (not the auto-generated UUID) so output is reproducible across runs — a UUID-ordering bug initially made multi-project output 30% flaky

Production-data verification continues to live alongside in `scripts/phase2_verify_byte_identical.py` + the five baselines under `tests/phase2_baseline/`.

### D.9 Worked example (multi-project gap scenario)

A two-project deal has a Sources/Uses gap on Project 1 because NOI doesn't support more debt at 1.15 DSCR. The user opens the slider drawer and:

1. Drags Purchase Price down $30k → phantom UseLine with `amount = -30000` materializes on Project 1, total Uses drops by ~$30k. The pill is now yellow ("⚠ Balanced w/ adjustments").
2. Notices the DSCR didn't move (PP doesn't affect NOI; the DSCR-cap loan size is unchanged). Drags Revenue +$500/mo → phantom IncomeStream materializes, NOI rises, sized loan rises to keep DSCR=1.15, the gap closes by another ~$60k.
3. Drags OpEx -$5k/yr → phantom OperatingExpenseLine with `annual_amount = -5000`, NOI rises further, sized loan rises again, gap closes.

The final state: three phantom rows persisted, pill yellow with "Balanced w/ adjustments", Sources = Uses, DSCR = 1.150, equity_required = 0. The model "pencils" but only via fictional inputs the user knows have to be operationalized (find the $500/mo from somewhere; find the $5k/yr opex savings; negotiate the $30k off PP).

When the user later finds real budget for any of those, they edit the underlying real lines (not the phantoms) and drag the corresponding slider back to zero. The pill goes green only when all three sliders are zero.

---

## Appendix F: Investor Excel Export — Formula-Driven Cells (May 2026)

The investor workbook ships with selected metric cells wired as live Excel formulas referencing **defined names** rather than engine-computed Decimals. LP edits to upstream input cells re-derive downstream metrics inside the workbook without re-running the Python engine.

Implementation lives in [`app/exporters/investor_export.py`](../app/exporters/investor_export.py). The `CellRegistry` (in [`_workbook_helpers.py`](../app/exporters/_workbook_helpers.py)) tracks every named cell so cross-sheet formulas resolve at workbook write time.

### F.1 Data-Point Catalog

Each row documents one data point: definition, named range, app-side calc, app-side caveats, Excel formula, Excel-side caveats, and a Refs column listing every other data point or named range mentioned in this row (for navigation + drift detection).

**Slug convention:** anchor for each Data Point = lowercase-hyphenated form of column A (e.g. "Going-In Cap Value" → `#going-in-cap-value`, "NOI" → `#noi`).

#### F.1.1 Returns / Profitability

##### Combined Equity Multiple

| Field | Value |
|---|---|
| **Definition** | Total equity distributions ÷ total equity contributions over hold. |
| **Named Range** | `s_combined_equity_multiple` (UW Summary), `s_returns_combined_em` (Investor Returns) |
| **App Calc/Use** | `app/exporters/investor_export.py:_combined_em` reads waterfall rollup; sum positive distributions ÷ sum negative contributions per equity module. |
| **App Notes** | Returns `None` when total committed equity < $1 (auto-funded deals); falls back to `totals.combined_em_x` for implied-equity scenarios. |
| **Excel Formula** | `=IFERROR(SUMIF(r_uw_cf_levered,">0")/(-SUMIF(r_uw_cf_levered,"<0")),0)` |
| **Excel Notes** | Operates on annual Levered Cash Flow row, not monthly. Equity-call timing differs from engine's monthly waterfall — parity is ±0.5x, not bit-for-bit. |
| **Refs** | [Levered Cash Flow](#levered-cash-flow), [s_combined_equity_multiple](#combined-equity-multiple), [s_returns_combined_em](#combined-equity-multiple), [r_uw_cf_levered](#levered-cash-flow) |

##### Combined Levered IRR

| Field | Value |
|---|---|
| **Definition** | Internal rate of return on the scenario's levered (after-debt) cash flow stream. |
| **Named Range** | `s_combined_irr` (UW Summary), `s_returns_combined_irr` (Investor Returns) |
| **App Calc/Use** | `app/engines/cashflow.py` computes `combined_irr_pct` via monthly XIRR over the period-level levered NCF; surfaced through `totals.combined_irr_pct`. |
| **App Notes** | Engine uses monthly XIRR with explicit dates; annualized for display. |
| **Excel Formula** | `s_returns_combined_irr` (Investor Returns) = `=IFERROR(IRR(r_uw_cf_levered),0)`. `s_combined_irr` (UW Summary, Phase 4 hero-KPI conversion, 2026-05-24) = `=IFERROR(s_returns_combined_irr,0)` — aliases the Returns formula rather than re-computing, so any upstream cash-flow edit ripples to both KPIs through the single underlying `IRR()` call. |
| **Excel Notes** | Excel `IRR()` assumes evenly-spaced annual periods. Parity with engine's monthly XIRR is ±0.5pp, not exact. IFERROR swallows the no-equity / degenerate-stream case as 0. |
| **Refs** | [Levered Cash Flow](#levered-cash-flow), [s_combined_irr](#combined-levered-irr), [s_returns_combined_irr](#combined-levered-irr), [r_uw_cf_levered](#levered-cash-flow) |

##### Yield on Cost

| Field | Value |
|---|---|
| **Definition** | Stabilized NOI ÷ Total Project Cost. Unlevered return on cost basis. |
| **Named Range** | `s_yield_on_cost` |
| **App Calc/Use** | `app/exporters/investor_export.py` computes as `combined_noi / total_uses` for the UW Summary KPI row. |
| **App Notes** | Stabilized = first 12 ops months per default NOI basis. |
| **Excel Formula** | `=IFERROR(s_combined_noi/s_su_uses_total,"")` |
| **Excel Notes** | Both operands are scenario-level named cells; LP edits to revenue/OpEx (through NOI) or Use-line amounts (through Total Uses) re-derive YoC inside the workbook. |
| **Refs** | [NOI](#noi), [Total Uses](#total-uses), [s_combined_noi](#noi), [s_su_uses_total](#total-uses), [s_yield_on_cost](#yield-on-cost) |

#### F.1.2 Valuation

##### Cap Spread

| Field | Value |
|---|---|
| **Definition** | Yield on Cost − Going-In Cap Rate. Positive = yield premium (creating value above market cap); negative = paying above-market cap. |
| **Named Range** | `s_cap_spread` |
| **App Calc/Use** | `app/exporters/investor_export.py` Property Valuation block; engine still computes raw value to drive the "Yield premium / discount" hint text. |
| **App Notes** | Hint text gated on `cap_spread > 0`. |
| **Excel Formula** | `=IFERROR(s_yield_on_cost-s_going_in_cap_rate,"")` |
| **Excel Notes** | Both operands are decimal fractions (e.g. 0.085 for 8.5%), so subtraction yields the spread directly. |
| **Refs** | [Yield on Cost](#yield-on-cost), [Going-In Cap Rate](#going-in-cap-rate), [s_yield_on_cost](#yield-on-cost), [s_going_in_cap_rate](#going-in-cap-rate), [s_cap_spread](#cap-spread) |

##### Exit Cap Value

| Field | Value |
|---|---|
| **Definition** | Market value at exit = Exit-Year NOI ÷ Exit Cap Rate. Reconciles against DCF NPV. |
| **Named Range** | `s_direct_cap_value` |
| **App Calc/Use** | `app/exporters/investor_export.py` Property Valuation block; engine still computes for hint text ("Market value at exit ({pct}% cap, Y{n} NOI)"). |
| **App Notes** | Exit year = `min(max(annual_periods), 10)`. |
| **Excel Formula** | `=IFERROR(s_exit_year_noi/s_exit_cap_rate,"")` |
| **Excel Notes** | `s_exit_year_noi` pointer = last column of UW Pro Forma NOI row, so edits to NOI growth chain feed through. |
| **Refs** | [NOI](#noi), [Exit Cap Rate](#exit-cap-rate), [s_exit_year_noi](#noi), [s_exit_cap_rate](#exit-cap-rate), [s_direct_cap_value](#exit-cap-value) |

##### Going-In Cap Value

| Field | Value |
|---|---|
| **Definition** | Market value at acquisition = stabilized NOI ÷ Going-In Cap Rate. |
| **Named Range** | `s_going_in_cap_value` |
| **App Calc/Use** | `app/exporters/investor_export.py` Property Valuation block; engine still computes for hint text. |
| **App Notes** | Uses stabilized (Y1) NOI, not exit-year. |
| **Excel Formula** | `=IFERROR(s_combined_noi/s_going_in_cap_rate,"")` |
| **Excel Notes** | LP edits to NOI (revenue / OpEx) and Going-In Cap input both flow through. |
| **Refs** | [NOI](#noi), [Going-In Cap Rate](#going-in-cap-rate), [s_combined_noi](#noi), [s_going_in_cap_rate](#going-in-cap-rate), [s_going_in_cap_value](#going-in-cap-value) |

#### F.1.3 Income / Operating

##### Asset Mgmt Fee

| Field | Value |
|---|---|
| **Definition** | Annual asset management fee charged to the scenario; modeled as a % of EGI. |
| **Named Range** | `s_asset_mgmt_fee` (the rate input on Assumptions) |
| **App Calc/Use** | `app/engines/cashflow.py` applies the fee as a monthly OpEx-adjacent line, debiting EGI. Pro Forma annual row aggregates monthly outlay. |
| **App Notes** | Stored as decimal fraction (0.03 = 3%). |
| **Excel Formula** | `=IFERROR(-{col}{egi_row}*s_asset_mgmt_fee,0)` |
| **Excel Notes** | One formula per year column; `{col}{egi_row}` resolves to the same column on the [EGI](#egi) row. Negative sign — outflow. |
| **Refs** | [EGI](#egi), [s_asset_mgmt_fee](#asset-mgmt-fee) |

##### Net Cash Flow (Pro Forma)

| Field | Value |
|---|---|
| **Definition** | NOI − Debt Service for the year. The "net" line before equity distributions. |
| **Named Range** | (per-year cell; not separately named) |
| **App Calc/Use** | `app/engines/cashflow.py` computes monthly NCF in `_compute_period`; annual aggregate emitted via `_DERIVED_FORMULA_FIELDS["net_cash_flow"] = ("+noi", "-debt_service")`. |
| **App Notes** | Excludes capital events (sale proceeds, refi) — those land on the Levered Cash Flow row instead. |
| **Excel Formula** | `={col}{noi_row}-{col}{ds_row}` |
| **Excel Notes** | Per-year derived formula, generated by `_DERIVED_FORMULA_FIELDS` in `_build_uw_proforma`. Operand rows guaranteed written first by row-order. |
| **Refs** | [NOI](#noi), [Debt Service](#debt-service) |

##### OpEx Y1 Sum (Block G chain seed)

| Field | Value |
|---|---|
| **Definition** | Pro Forma Y1 Operating Expenses = SUM of every `s_opex_<slug>_annual` cell on Assumptions Block G. LP edits to any OpEx line's annual amount ripple to Y1, then forward via the Y2+ growth chain. |
| **Named Range** | (cell-only — no defined name; the Pro Forma Y1 cell carries the formula) |
| **App Calc/Use** | `_build_uw_proforma._opex_y1_formula()` enumerates `_all_opex_slugs(ctx).values()` and emits `=SUM(s_opex_<s1>_annual, s_opex_<s2>_annual, …)`. |
| **App Notes** | Replaces the prior engine-value seed for Y1. Y0 still keeps engine value because construction-phase OpEx differs from stabilized inputs. |
| **Excel Formula** | `=SUM(s_opex_1_annual,s_opex_2_annual,…)` |
| **Excel Notes** | One ref per `OperatingExpenseLine` record across all projects, slugs from `_all_opex_slugs`. When no OpEx records exist the cell falls back to the engine value. |
| **Refs** | [OpEx Annual](#opex-annual), [OpEx Growth Chain (Y2+)](#opex-growth-chain-y2), [s_opex_n_annual](#opex-annual) |

##### Revenue Per-Stream Breakout (Pro Forma transparency block)

| Field | Value |
|---|---|
| **Definition** | One indented row per `IncomeStream` rendered directly below the Pro Forma's Gross Revenue total, exposing each stream's annual ramp so the LP can trace any single revenue line back to its Assumptions Block F input. Symmetric to the OpEx per-line breakout — total row left unchanged. |
| **Named Range** | (cell-only — breakout rows are read-only references, no defined names) |
| **App Calc/Use** | `_build_uw_proforma` walks `_all_revenue_streams_ordered(ctx)` after writing the Gross Revenue total row and emits one breakout per stream using the slug from `_all_revenue_slugs(ctx)`. |
| **App Notes** | Y0 left blank (construction-phase revenue is engine-governed via lease-up ramp, not derivable from stabilized inputs). Y1 = the stream's `s_rev_<slug>_y1_monthly` cell × 12. Y2+ = prior-year breakout cell × (1 + per-stream `s_rev_<slug>_escalation_pct`), so rent-controlled and market-rate units can ramp at their own rates rather than the sheet-wide `s_revenue_growth_rate`. |
| **Excel Formula** | Y1 = `=s_rev_<slug>_y1_monthly*12`; Y2+ = `={col-1}{row}*(1+s_rev_<slug>_escalation_pct)` |
| **Excel Notes** | Labels start with the ``   •`` indent marker; hint font (italic, muted color) reinforces "transparency, not a primary KPI". Mirror of the OpEx Per-Line Breakout entry below. |
| **Refs** | [Revenue Y1 Sum (Block F chain seed)](#revenue-y1-sum-block-f-chain-seed), [OpEx Per-Line Breakout (Pro Forma transparency block)](#opex-per-line-breakout-pro-forma-transparency-block) |

##### OpEx Per-Line Breakout (Pro Forma transparency block)

| Field | Value |
|---|---|
| **Definition** | One indented row per `OperatingExpenseLine` rendered directly below the Pro Forma's Operating Expenses total, exposing each line's annual ramp so the LP can trace any single expense back to its Assumptions Block G input. The total row is left unchanged — these are pure transparency rows, not summed back into anything downstream. |
| **Named Range** | (cell-only — breakout rows are read-only references, no defined names) |
| **App Calc/Use** | `_build_uw_proforma` walks `_all_opex_lines_ordered(ctx)` after writing the OpEx total row and emits one breakout per line using the slug from `_all_opex_slugs(ctx)`. |
| **App Notes** | Y0 left blank (construction-phase OpEx is engine-governed, not derivable from stabilized inputs). Y1 = the line's `s_opex_<slug>_annual` cell. Y2+ = prior-year breakout cell × (1 + per-line `s_opex_<slug>_escalation_pct`), so heterogeneous escalation rates render correctly — each line ramps at its own rate rather than the sheet-wide `s_opex_growth_rate`. |
| **Excel Formula** | Y1 = `=s_opex_<slug>_annual`; Y2+ = `={col-1}{row}*(1+s_opex_<slug>_escalation_pct)` |
| **Excel Notes** | Labels start with the ``   •`` indent marker so the LP visually parses them as a sub-list of the Operating Expenses total. Hint font (italic, muted color) reinforces "transparency, not a primary KPI". |
| **Refs** | [OpEx Y1 Sum (Block G chain seed)](#opex-y1-sum-block-g-chain-seed), [OpEx Annual](#opex-annual) |

##### OpEx Growth Chain (Y2+)

| Field | Value |
|---|---|
| **Definition** | Operating expenses for Year N = Year N−1 × (1 + OpEx growth rate). |
| **Named Range** | `s_opex_growth_rate` |
| **App Calc/Use** | `app/engines/cashflow.py` applies escalation factor to monthly OpEx lines based on each line's `escalation_rate_pct`; Pro Forma annual row aggregates. |
| **App Notes** | Engine supports per-line escalation rates; Excel chain uses one scenario-wide growth rate as a simplification. Y0 keeps engine value as seed; Y1 is now formula-driven via [OpEx Y1 Sum (Block G chain seed)](#opex-y1-sum-block-g-chain-seed). |
| **Excel Formula** | `={col-1}{exp_row}*(1+s_opex_growth_rate)` |
| **Excel Notes** | Diverges from engine when expense lines have heterogeneous escalation rates. Same chain feeds CapEx Reserve row. |
| **Refs** | [s_opex_growth_rate](#opex-growth-chain-y2), [OpEx Y1 Sum (Block G chain seed)](#opex-y1-sum-block-g-chain-seed) |

##### Revenue Y1 Sum (Block F chain seed)

| Field | Value |
|---|---|
| **Definition** | Pro Forma Y1 Gross Revenue = SUM of every `s_rev_<slug>_y1_monthly` cell on Assumptions Block F, annualized × 12. LP edits to a stream's unit count / rent / occupancy on Assumptions ripple to Y1, then forward via the Y2+ growth chain. |
| **Named Range** | (cell-only — no defined name; the Pro Forma Y1 cell carries the formula) |
| **App Calc/Use** | `_build_uw_proforma._gross_revenue_y1_formula()` enumerates `_all_revenue_slugs(ctx).values()` and emits `=SUM(s_rev_<s1>_y1_monthly, …)*12`. |
| **App Notes** | Replaces the prior engine-value seed for Y1. Y0 still keeps engine value because construction-phase revenue is governed by lease-up ramp / pre-stabilized engine math, not the stabilized Y1 inputs. |
| **Excel Formula** | `=SUM(s_rev_1_y1_monthly,s_rev_2_y1_monthly,…)*12` |
| **Excel Notes** | Annualization wraps the whole SUM via the outer `*12` (each stream's `y1_monthly` cell already reflects unit count × rent × occupancy via Block F's IFERROR formula). |
| **Refs** | [Stream Y1 Monthly](#stream-y1-monthly), [Revenue Growth Chain (Y2+)](#revenue-growth-chain-y2), [s_rev_n_y1_monthly](#stream-y1-monthly) |

##### Revenue Growth Chain (Y2+)

| Field | Value |
|---|---|
| **Definition** | Gross revenue for Year N = Year N−1 × (1 + revenue growth rate). |
| **Named Range** | `s_revenue_growth_rate` |
| **App Calc/Use** | `app/engines/cashflow.py` applies per-stream escalation rates to monthly revenue; Pro Forma annual row aggregates to year totals. |
| **App Notes** | Engine default uses per-stream `escalation_rate_pct`; Excel chain collapses to a scenario-wide growth rate seeded by unit-count-weighted mean of stream escalations (`_revenue_growth_default`). Y0 keeps engine value as seed; Y1 is now formula-driven via [Revenue Y1 Sum (Block F chain seed)](#revenue-y1-sum-block-f-chain-seed). |
| **Excel Formula** | `={col-1}{rev_row}*(1+s_revenue_growth_rate)` |
| **Excel Notes** | Chain compounds Y2+. Diverges from engine for streams with non-default escalation. |
| **Refs** | [s_revenue_growth_rate](#revenue-growth-chain-y2) |

#### F.1.4 Debt

##### Amort Annual Payment (per year)

| Field | Value |
|---|---|
| **Definition** | Total P&I outlay for the year on the perm-loan amortization table. |
| **Named Range** | (per-cell, not named) |
| **App Calc/Use** | Pre-formula: engine computed via `_monthly_pmt × 12`. Now formula-only. |
| **App Notes** | During IO window: equals interest only (no principal reduction). |
| **Excel Formula** | `=IF($G${perm_row}>={end_period}, $C${perm_row}*$D${perm_row}, IFERROR(-PMT($D${perm_row}/12,$F${perm_row}*12,$C${perm_row})*12,0))` |
| **Excel Notes** | References Loan Summary cells: C=principal, D=rate, F=amort yrs, G=IO months. IO branch fires when IO months cover the year-end month. |
| **Refs** | [Loan Summary](#loan-summary) |

##### Amort Beginning Balance

| Field | Value |
|---|---|
| **Definition** | Loan balance at start of year on the perm-loan amortization table. |
| **Named Range** | (per-cell, not named) |
| **App Calc/Use** | Pre-formula: engine computed via `_balloon_balance`. Now formula-only. |
| **App Notes** | Year 1 pulls principal; Year N reads prior year's End Balance. |
| **Excel Formula** | Y1: `=$C${perm_row}` (absolute principal ref); Y2+: `=F{prev_row}` (prior End Balance) |
| **Excel Notes** | Chain breaks if amort table is reordered; relative refs intentional. |
| **Refs** | [Loan Summary](#loan-summary) |

##### Amort Ending Balance

| Field | Value |
|---|---|
| **Definition** | Loan balance at end of year = Beginning Balance − Principal Paid. |
| **Named Range** | (per-cell, not named) |
| **App Calc/Use** | Pre-formula: engine `_balloon_balance(end-of-year)`. Now formula-only derivation. |
| **App Notes** | Should reach 0 at amort-term-end year (sweep enforced naturally by CUMPRINC chain). |
| **Excel Formula** | `=B{cur_row}-E{cur_row}` |
| **Excel Notes** | Pure cell arithmetic; no named-range refs. |
| **Refs** | (none) |

##### Amort Interest (per year)

| Field | Value |
|---|---|
| **Definition** | Interest portion of the year's debt service on the perm-loan amortization table. |
| **Named Range** | (per-cell, not named) |
| **App Calc/Use** | Pre-formula: engine computed via average-balance approximation (`(beg + end) / 2 × rate × 12`). Now formula uses Excel's `CUMIPMT`. |
| **App Notes** | Engine average-balance was display-only; period-level cashflow uses `period_interest_months` with actual day-count. |
| **Excel Formula** | `=IF($G${perm_row}>={end_period}, $C${perm_row}*$D${perm_row}, IFERROR(-CUMIPMT($D${perm_row}/12,$F${perm_row}*12,$C${perm_row},{start_period},{end_period},0),0))` |
| **Excel Notes** | CUMIPMT returns negative under Excel sign convention; negated. IO branch: interest = principal × rate. |
| **Refs** | [Loan Summary](#loan-summary) |

##### Amort Principal (per year)

| Field | Value |
|---|---|
| **Definition** | Principal portion of the year's debt service = Annual Payment − Interest. |
| **Named Range** | (per-cell, not named) |
| **App Calc/Use** | Pre-formula: engine derived from `_balloon_balance` deltas. Now formula-only. |
| **App Notes** | Zero during IO window. |
| **Excel Formula** | `=C{cur_row}-D{cur_row}` |
| **Excel Notes** | Pure cell arithmetic; no named-range refs. Equivalent to `CUMPRINC` but cheaper as a derivation from already-computed neighbors. |
| **Refs** | (none) |

##### Annual P&I (pi loans, Loan Summary)

| Field | Value |
|---|---|
| **Definition** | Annual principal + interest payment for an amortizing (`carry_type == "pi"`) loan. |
| **Named Range** | `s_loan_{n}_annual_pi` (one per pi loan, n = 1-based index) |
| **App Calc/Use** | `app/engines/cashflow.py` `_monthly_pmt(...)*12` for engine-side aggregation. |
| **App Notes** | Other carry types (`io_only`, `interest_reserve`, `capitalized_interest`) leave this cell at engine value (or em-dash) — formula path skipped because annual outlay isn't a simple PMT. |
| **Excel Formula** | `=IFERROR(PMT(D{r}/12,F{r}*12,-C{r})*12,0)` |
| **Excel Notes** | References Loan Summary cells: C=principal, D=rate (fraction), F=amort yrs. Negative principal flips PMT sign so result is positive annual payment. |
| **Refs** | [Loan Summary](#loan-summary), [s_loan_n_annual_pi](#annual-pi-pi-loans-loan-summary) |

##### Debt Service (Pro Forma per year)

| Field | Value |
|---|---|
| **Definition** | Total debt service for the year, summed across all PMT-eligible loans active in that year. |
| **Named Range** | (per-cell on the Debt Service row; not separately named) |
| **App Calc/Use** | `app/engines/cashflow.py` sums period-level interest + principal across all debt modules per loan's active window (`_loan_pre_op_months`). |
| **App Notes** | Engine respects per-loan `active_phase_start/end`. Excel formula gates by both `term_months` (hold end) and, when registered, `perm_origination_month` (start of operations) — closes the prior Y1 overstatement for construction-to-perm stacks. Loans with no registered perm cell (pure-acquisition scenarios, loans funding only ineligible projects) keep the legacy term-only gate. Single-project value_add / new-construction scenarios get the perm-gated form since Block E on Assumptions emits `p1_perm_origination_month`. |
| **Excel Formula** | `=IF(AND(s_loan_1_term_months>={y*12},{y*12}>=s_loan_1_perm_origination_month),s_loan_1_annual_pi,0)+IF(s_loan_2_term_months>={y*12},s_loan_2_annual_pi,0)+…` (per-loan: `AND(...)` form when the loan has a registered perm cell, legacy term-only form otherwise) |
| **Excel Notes** | Per-year formula, threshold scales with the column's year. Y0 keeps engine value (construction-phase DS differs from stabilized PMT). |
| **Refs** | [Loan Summary](#loan-summary), [Annual P&I](#annual-pi-pi-loans-loan-summary), [Loan Perm Origination Month](#loan-perm-origination-month), [s_loan_n_term_months](#loan-summary), [s_loan_n_annual_pi](#annual-pi-pi-loans-loan-summary), [s_loan_n_perm_origination_month](#loan-perm-origination-month) |

##### Loan Summary

| Field | Value |
|---|---|
| **Definition** | Per-loan reference row on the Debt Schedule. Columns: Label, Funder, Principal (C), Rate (D), Term-months (E), Amort-yrs (F), IO-months (G), Carry, Day-Count, Annual P&I, Balloon. |
| **Named Range** | `s_loan_{n}_principal`, `s_loan_{n}_rate`, `s_loan_{n}_term_months`, `s_loan_{n}_annual_pi`, `s_loan_{n}_balloon` (one set per debt module) |
| **App Calc/Use** | `app/exporters/investor_export.py:_build_debt_schedule` enumerates debt modules, writes one row per loan, registers per-cell named ranges so downstream formulas can ref them. |
| **App Notes** | Index `n` is 1-based and matches enumeration order — same order used by `_pmt_loan_indices` for Pro Forma DS SUM. |
| **Excel Formula** | (input cells, not formulas) |
| **Excel Notes** | Annual P&I cell on this row IS a formula for `pi`-carry loans — see [Annual P&I](#annual-pi-pi-loans-loan-summary). |
| **Refs** | [Annual P&I](#annual-pi-pi-loans-loan-summary), [s_loan_n_principal](#loan-summary), [s_loan_n_rate](#loan-summary), [s_loan_n_term_months](#loan-summary), [s_loan_n_annual_pi](#annual-pi-pi-loans-loan-summary), [s_loan_n_balloon](#loan-summary) |

#### F.1.5 Cover sheet

##### Cover Hero — Cap Rate

| Field | Value |
|---|---|
| **Definition** | Top-of-Cover snapshot of yield on cost. |
| **Named Range** | (cell on Cover; not separately named) |
| **App Calc/Use** | Cross-sheet ref to [Yield on Cost](#yield-on-cost) named range. |
| **App Notes** | Cover renders before UW sheets; formula evaluation defers to Excel calc engine. |
| **Excel Formula** | `=s_combined_noi/s_su_uses_total` |
| **Excel Notes** | Same operands as YoC but unwrapped IFERROR — assumes the UW Summary already validates non-zero denominator. |
| **Refs** | [NOI](#noi), [Total Uses](#total-uses), [Yield on Cost](#yield-on-cost), [s_combined_noi](#noi), [s_su_uses_total](#total-uses) |

##### Cover Hero — IRR

| Field | Value |
|---|---|
| **Definition** | Top-of-Cover snapshot of Combined Levered IRR. |
| **Named Range** | (cell on Cover; not separately named) |
| **App Calc/Use** | Cross-sheet ref to [Combined Levered IRR](#combined-levered-irr) named range. |
| **App Notes** | Only emitted when profile renders UW Summary (so the named range exists). |
| **Excel Formula** | `=s_combined_irr` |
| **Excel Notes** | Pure cross-sheet ref. |
| **Refs** | [Combined Levered IRR](#combined-levered-irr), [s_combined_irr](#combined-levered-irr) |

##### Cover Hero — NOI

| Field | Value |
|---|---|
| **Definition** | Top-of-Cover snapshot of stabilized NOI. |
| **Named Range** | (cell on Cover; not separately named) |
| **App Calc/Use** | Cross-sheet ref to [NOI](#noi) named range. |
| **App Notes** | Same gating as Cap Rate / IRR hero cells. |
| **Excel Formula** | `=s_combined_noi` |
| **Excel Notes** | Pure cross-sheet ref. |
| **Refs** | [NOI](#noi), [s_combined_noi](#noi) |

#### F.1.6 Engine-driven inputs + aggregates

These data points have a named cell on the workbook (so Excel formulas can reference them) but their *primary* computation lives in the engine. The cell value is an engine write, not a formula.

##### Debt Service

| Field | Value |
|---|---|
| **Definition** | Total interest + principal outlay per period across all active debt modules. |
| **Named Range** | (annual aggregate row on Underwriting Cash Flow; not separately named — referenced positionally) |
| **App Calc/Use** | `app/engines/cashflow.py` sums `period_interest_months` + principal amortization per loan's active window; aggregated to annual columns in `app/exporters/investor_export.py:_build_uw_cashflow`. |
| **App Notes** | Per-loan `active_phase_start/end` controls which periods contribute. Construction-phase debt service differs from stabilized PMT — see [Annual P&I](#annual-pi-pi-loans-loan-summary). |
| **Excel Formula** | `—` (engine-written value; the Pro Forma version is [Debt Service (Pro Forma per year)](#debt-service-pro-forma-per-year), which IS a formula) |
| **Excel Notes** | Annual aggregate over monthly periods loses sub-month precision. |
| **Refs** | [Annual P&I](#annual-pi-pi-loans-loan-summary), [Debt Service (Pro Forma per year)](#debt-service-pro-forma-per-year) |

##### EGI

| Field | Value |
|---|---|
| **Definition** | Effective Gross Income = Gross Revenue × (1 − vacancy). Pre-OpEx, post-vacancy income. |
| **Named Range** | (per-year cell on Pro Forma row; not separately named) |
| **App Calc/Use** | `app/engines/cashflow.py:_compute_period` applies stream-level vacancy + occupancy ramp to monthly Gross Revenue; annual EGI on the Pro Forma is the year-sum. |
| **App Notes** | Vacancy is `1 − occupancy_pct`; occupancy uses a lease-up curve during the lease-up phase, snaps to stabilized after. |
| **Excel Formula** | `—` (engine-written annual value) |
| **Excel Notes** | Referenced positionally by the [Asset Mgmt Fee](#asset-mgmt-fee) formula (`{col}{egi_row}`). If the EGI row moves rows, the Asset Mgmt Fee `{egi_row}` placeholder needs to be re-resolved during emit. |
| **Refs** | [Asset Mgmt Fee](#asset-mgmt-fee) |

##### Exit Cap Rate

| Field | Value |
|---|---|
| **Definition** | Discount rate applied to exit-year NOI to derive sale-time market value. Driver of terminal value in DCF / waterfall. |
| **Named Range** | `s_exit_cap_rate` |
| **App Calc/Use** | User-editable cell on Assumptions Block A; default from `Scenario.exit_cap_rate_pct` or org default. `_pct_value` converts the stored whole-percent (e.g. 6.5) to a decimal fraction (0.065). |
| **App Notes** | Stored as decimal fraction in the named cell; **not** as whole-number percent. Formulas dividing by this cell get correct value directly. |
| **Excel Formula** | (input cell, no formula) |
| **Excel Notes** | LP-editable; edits flow through to [Exit Cap Value](#exit-cap-value). Format is PCT (renders as percent but stored as fraction). |
| **Refs** | [Exit Cap Value](#exit-cap-value), [s_exit_cap_rate](#exit-cap-rate) |

##### Going-In Cap Rate

| Field | Value |
|---|---|
| **Definition** | Capitalization rate at acquisition; used to derive market value from stabilized NOI. |
| **Named Range** | `s_going_in_cap_rate` |
| **App Calc/Use** | User-editable cell on Assumptions Block A; default from `Scenario.going_in_cap_rate_pct` or org default. `_pct_value` divides by 100 to store as fraction. |
| **App Notes** | Stored as decimal fraction; same convention as [Exit Cap Rate](#exit-cap-rate). |
| **Excel Formula** | (input cell, no formula) |
| **Excel Notes** | LP-editable; edits flow through to [Going-In Cap Value](#going-in-cap-value) and [Cap Spread](#cap-spread). |
| **Refs** | [Going-In Cap Value](#going-in-cap-value), [Cap Spread](#cap-spread), [Exit Cap Rate](#exit-cap-rate), [s_going_in_cap_rate](#going-in-cap-rate) |

##### Levered Cash Flow

| Field | Value |
|---|---|
| **Definition** | Net cash flow available to equity per period = NCF − Debt Service + Capital Events − Equity Calls. |
| **Named Range** | `r_uw_cf_levered` (annual row range on Underwriting Cash Flow) |
| **App Calc/Use** | `app/engines/cashflow.py` computes monthly per-period; `_build_uw_cashflow` aggregates to annual columns and registers `r_uw_cf_levered` as the row range. |
| **App Notes** | Includes capital events (sale proceeds, refi) and equity calls — distinct from [Net Cash Flow (Pro Forma)](#net-cash-flow-pro-forma) which excludes both. |
| **Excel Formula** | (annual row; per-cell engine-written) |
| **Excel Notes** | Consumed by [Combined Levered IRR](#combined-levered-irr) via `IRR()` and [Combined Equity Multiple](#combined-equity-multiple) via `SUMIF`. Annual aggregation loses sub-year equity-call/distribution timing — primary parity gap vs engine's monthly XIRR. |
| **Refs** | [NOI](#noi), [Debt Service](#debt-service), [Combined Levered IRR](#combined-levered-irr), [Combined Equity Multiple](#combined-equity-multiple), [Net Cash Flow (Pro Forma)](#net-cash-flow-pro-forma), [r_uw_cf_levered](#levered-cash-flow) |

##### NOI

| Field | Value |
|---|---|
| **Definition** | Net Operating Income = EGI − Operating Expenses. The fundamental income measure for cap-rate valuation. |
| **Named Range** | `s_combined_noi` (stabilized aggregate, scenario-level); `s_exit_year_noi` (last column of UW Pro Forma NOI row, used for terminal-value math). |
| **App Calc/Use** | `app/engines/cashflow.py:_compute_period` produces monthly NOI; `totals.noi_stabilized` aggregates the stabilized-window months. `_build_uw_summary` registers `s_combined_noi`. The UW Pro Forma NOI row is per-year aggregate; `s_exit_year_noi` points at its last column. |
| **App Notes** | Stabilized = first 12 months of the stabilized phase. Edits to revenue / OpEx flow through monthly engine → annual aggregate → named range. |
| **Excel Formula** | (engine-written value; consumed by formulas elsewhere) |
| **Excel Notes** | `s_combined_noi` is the Y1-stabilized number; `s_exit_year_noi` is Y_N where N = exit year. They differ when the OpEx/revenue growth chains compound. Formulas referencing the wrong one give materially wrong cap values. |
| **Refs** | [EGI](#egi), [Yield on Cost](#yield-on-cost), [Going-In Cap Value](#going-in-cap-value), [Exit Cap Value](#exit-cap-value), [Cover Hero — NOI](#cover-hero-noi), [s_combined_noi](#noi), [s_exit_year_noi](#noi) |

##### Total Uses

| Field | Value |
|---|---|
| **Definition** | Sum of all UseLine amounts in the scenario excluding the `exit` phase. The denominator of cost-basis metrics like Yield on Cost. |
| **Named Range** | `s_su_uses_total` |
| **App Calc/Use** | `app/exporters/investor_export.py:_build_su_sheet` aggregates `UseLine.amount` per cost category, then totals; the engine value `total_project_cost` in `OperationalOutputs` is the same number per project, summed across projects. |
| **App Notes** | Excludes `phase=exit` UseLines (selling costs, exit fees) — those are netted from sale proceeds, not part of acquisition basis. |
| **Excel Formula** | (engine-written value; consumed by formulas elsewhere) |
| **Excel Notes** | Consumed by [Yield on Cost](#yield-on-cost) and [Cover Hero — Cap Rate](#cover-hero-cap-rate). Edits to UseLines on the S&U sheet re-derive this via the sheet's own SUM formulas (S&U Use rows are formulas — see S&U documentation in the formula-conversion plan). |
| **Refs** | [Yield on Cost](#yield-on-cost), [Cover Hero — Cap Rate](#cover-hero-cap-rate), [s_su_uses_total](#total-uses) |

#### F.1.7 Underwriting metrics (engine-only, no Excel formula)

These are LP-facing metrics the engine computes for the Underwriting Summary / Investor Returns sheets but does not yet expose as formula-driven cells. Workbook cells hold the engine value; LP edits to upstream inputs do **not** propagate without re-running the Python engine.

##### Cash-on-Cash (Year 1)

| Field | Value |
|---|---|
| **Definition** | Year-1 cash distributions to equity ÷ equity contributed. |
| **Named Range** | `s_coc_year_one` |
| **App Calc/Use** | `app/exporters/investor_export.py:_coc_year_one` sums waterfall `cash_distributed` for periods 1–12 across equity modules; divides by total equity commitments. |
| **App Notes** | Returns `None` when committed equity is $0 (auto-funded deals); falls back to scenario `equity_required` × Y1 distributions as the denominator. |
| **Excel Formula** | Phase 4 KPI-tail conversion (2026-05-25): `=IFERROR(MAX(0,INDEX(r_uw_cf_levered,1,1))/s_equity_required, <engine_fallback>)`. `INDEX(...,1,1)` picks the first column of `r_uw_cf_levered` — which IS Y1 because `year_cols` on the Underwriting Cash Flow sheet starts at 1 (the Y0 acquisition stub is intentionally skipped on that sheet). `MAX(0, ...)` clamps the negative-Y1 case (equity call in year one) so a deal still ramping shows 0% CoC rather than a misleading negative. LP edits to NOI, debt service, or capital events on the Y1 column, or to Equity Required, ripple to CoC Y1 without re-running the engine. |
| **Excel Notes** | Engine sums per-period waterfall `cash_distributed` across periods 1–12 (monthly grain) for equity tiers only; Excel formula uses annual aggregated Levered CF (sum of all tier distributions). Same approximation envelope as the Combined EM / WEM formulas on this row group. IFERROR catches the zero-equity / unconfigured-waterfall degenerate cases by falling back to the engine value. |
| **Refs** | [Combined Equity Multiple](#combined-equity-multiple), [s_coc_year_one](#cash-on-cash-year-1) |

##### DCF NPV

| Field | Value |
|---|---|
| **Definition** | Net Present Value of levered cash flows at the configured hurdle rate. NPV > 0 = asset clears the hurdle; NPV < 0 = doesn't. |
| **Named Range** | `s_dcf_npv` |
| **App Calc/Use** | `app/exporters/investor_export.py:_npv_levered` discounts waterfall distributions and equity calls at `s_discount_rate`; subtracts initial equity contribution. |
| **App Notes** | Hint text gates on `npv_lev > 0` to show "Value created above hurdle" vs "Return below hurdle". |
| **Excel Formula** | `—` (engine value; could become `=IFERROR(NPV(s_discount_rate,r_uw_cf_levered),0)` but Excel `NPV` assumes period-1 start, not period-0; needs an explicit Y0 add-back. Deferred.) |
| **Excel Notes** | Excel `NPV` discounts from period 1, not period 0 — naive conversion would understate NPV by the discount on the Y0 equity call. Use `XNPV` with explicit dates for parity. |
| **Refs** | [Combined Levered IRR](#combined-levered-irr), [Levered Cash Flow](#levered-cash-flow), [s_dcf_npv](#dcf-npv) |

##### DSCR (Minimum, Stabilized)

| Field | Value |
|---|---|
| **Definition** | Debt Service Coverage Ratio = NOI ÷ Debt Service, minimum across all stabilized periods. Bank's primary debt-sizing constraint. |
| **Named Range** | (not yet exposed as a named cell) |
| **App Calc/Use** | `app/engines/underwriting.py:MetricsCalculator.calculate_dscr` takes per-period `dscr_for_period` from `CashFlowPeriod` (which is `noi / debt_service` per month), filters to stabilized periods, returns min + average. |
| **App Notes** | When `debt_sizing_mode == "dscr_capped"`, the auto-sizer uses Newton-Raphson (`app/engines/newton_solve.py:solve_principal_for_dscr`) to size the loan such that the minimum DSCR exactly meets the target. |
| **Excel Formula** | `—` (engine value only) |
| **Excel Notes** | Could be formulized as `MIN(NOI_row/DS_row)` over the operating-period columns once a per-period DSCR row is named. The Debt Schedule's [Notes block](#debt-service-pro-forma-per-year) calls out when DSCR-cap was binding so the LP doesn't miss that the loan didn't size to LTV/LTC. |
| **Refs** | [NOI](#noi), [Debt Service](#debt-service) |

##### LTC (Loan-to-Cost)

| Field | Value |
|---|---|
| **Definition** | Total debt principal ÷ Total Project Cost. Bank's cost-basis lending limit. |
| **Named Range** | (not yet exposed) |
| **App Calc/Use** | `app/engines/underwriting.py:MetricsCalculator.calculate_ltc` sums debt module principals, divides by `total_project_cost` from `OperationalOutputs`. |
| **App Notes** | Auto-sizer respects `max_ltc_pct` from each loan's source config (default 75% for senior debt, see `_DEFAULT_LOAN_COSTS` in `cashflow.py`). |
| **Excel Formula** | `—` (engine value only) |
| **Excel Notes** | Could be formulized as `=SUM(s_loan_*_principal)/s_su_uses_total` once `SUMPRODUCT` or per-loan addition is wired (similar pattern to [Debt Service (Pro Forma per year)](#debt-service-pro-forma-per-year)). Deferred. |
| **Refs** | [Total Uses](#total-uses), [Loan Summary](#loan-summary) |

##### Operating Reserve

| Field | Value |
|---|---|
| **Definition** | Cash held aside at stabilization to cover N months of OpEx + Debt Service. A bank covenant + LP risk buffer. |
| **Named Range** | `s_operating_reserve_months` (the input — months count), `s_operating_reserve_dollars` (the derived $ amount as a UseLine, formula-driven on S&U) |
| **App Calc/Use** | `app/engines/cashflow.py` sizes the UseLine as `max(OpEx_monthly, DS_monthly) × reserve_months`, where `DS_monthly` is the stabilized PI payment. The `max()` ensures the reserve floor covers whichever is larger — important when debt service exceeds operating expenses. |
| **App Notes** | Pre-funded at closing as a Use line. Not drawn down in the cashflow model (stabilized operations are cash-flow positive); functions as a stress buffer for unexpected vacancy or expense spikes. |
| **Excel Formula** | S&U "Operating Reserve" row: `=s_operating_reserve_months * MAX(s_y1_opex, s_pf_debt_service_y1) / 12`. Both named ranges exist in the export registry. |
| **Excel Notes** | Two related cells: input months (`s_operating_reserve_months`) and derived dollars (`s_operating_reserve_dollars`). Both LP-editable indirectly via the months input. |
| **Refs** | [Total Uses](#total-uses), [s_operating_reserve_months](#operating-reserve) |

##### Total Project Cost (TPC)

| Field | Value |
|---|---|
| **Definition** | Sum of all hard costs, soft costs, financing costs, and reserves needed to acquire + build + stabilize the project. Synonymous with Total Uses excluding exit-phase costs. |
| **Named Range** | Same as [Total Uses](#total-uses) at the scenario level (`s_su_uses_total`). |
| **App Calc/Use** | `app/engines/cashflow.py:_calculate_total_project_cost` sums all `CashFlowLineItem` amounts excluding the `exit` phase per project; engine emits as `OperationalOutputs.total_project_cost`. |
| **App Notes** | The auto-sizer's one-pass divisor fold-in (`_auto_size_debt_modules`) ensures closing-cost UseLines are included in TPC so Sources = Uses balance holds. |
| **Excel Formula** | `—` (engine value; identical to [Total Uses](#total-uses) in scenario aggregate) |
| **Excel Notes** | Per-project TPC is on each project's per-project sheet (when present); scenario TPC is on S&U via [Total Uses](#total-uses). |
| **Refs** | [Total Uses](#total-uses) |

##### Weighted Equity Multiple

| Field | Value |
|---|---|
| **Definition** | Risk-adjusted EM that incorporates the time value of money at the hurdle rate. `(Equity + NPV) / Equity`. Always ≥ 1.0 when NPV ≥ 0. |
| **Named Range** | `s_weighted_equity_multiple` |
| **App Calc/Use** | `app/exporters/investor_export.py:_weighted_em_calc` reads `_npv_levered` (DCF NPV) and divides by equity required. |
| **App Notes** | Returns `None` when `equity_required < $1`. Hurdle rate from `Scenario.discount_rate_pct` (default 8% or org default). |
| **Excel Formula** | Phase 4 KPI-tail conversion (2026-05-25): `=IFERROR(SUMPRODUCT((r_uw_cf_levered>0)*r_uw_cf_levered/(1+s_discount_rate)^(COLUMN(r_uw_cf_levered)-MIN(COLUMN(r_uw_cf_levered))))/s_equity_required, <engine_fallback>)`. Uses annual SUMPRODUCT discounting over the Underwriting Cash Flow levered row (net-to-equity after debt service) at the user-editable Block A discount rate. LP edits to the hurdle, to any revenue / OpEx / debt-service cell, or to the equity-required denominator all ripple to WEM without re-running the engine. |
| **Excel Notes** | Engine uses **monthly** periods with `t/12` exponent against **equity-tier-only** waterfall distributions; Excel formula uses **annual** periods and the **aggregate** levered CF (sum of all tier distributions per period). Same approximation envelope as the Combined Equity Multiple formula already shipped on this row group — typical parity ±0.1×, worst case ±0.3× when waterfall has meaningful non-equity tiers. IFERROR catches zero-equity / no-distributions degenerate cases by falling back to the engine value. |
| **Refs** | [Combined Equity Multiple](#combined-equity-multiple), [DCF NPV](#dcf-npv), [s_weighted_equity_multiple](#weighted-equity-multiple) |

#### F.1.8 Per-project phase plan (absolute month boundaries)

These cells expose each project's phase boundaries as 1-based absolute month indices. They are computed by `app/engines/phase_plan.py:build_project_phase_windows` (which wraps the engine's `_build_phase_plan` to fold cumulative durations into `(start_month, end_month)` pairs) and registered by `app/exporters/investor_export.py:_emit_phase_plan_block`. The cells are the foundation for formula-driven construction-to-perm origination gating — a permanent-debt formula can reference `p<n>_perm_origination_month` directly instead of re-walking the milestone trigger chain.

**Host sheet routing:**
- **Multi-project scenarios** — emitted on each `P{n} <Name>` per-project sheet inside `_build_project_sheet`.
- **Single-project scenarios** — the per-project sheet is suppressed (noise reduction since it would duplicate Underwriting Pro Forma), so the block is emitted on the Assumptions sheet under **Block E: Phase Plan (Per Project)**. Cell names are identical (`p1_*`) so downstream consumers like the Debt Schedule's C2P Status block and the Pro Forma Debt Service formula resolve unchanged in both layouts.

##### Phase Start Month

| Field | Value |
|---|---|
| **Definition** | Absolute, 1-based month index when a phase begins on a project's timeline. Acquisition is always month 1. |
| **Named Range** | `p<n>_phase_<phase>_start_month` (e.g. `p1_phase_construction_start_month`, `p1_phase_stabilized_start_month`) |
| **App Calc/Use** | `build_project_phase_windows` folds the cumulative sum of phase durations from `_build_phase_plan`. Phase membership rules (which phases apply to which project type) are unchanged — this only adds the absolute-month coordinate. |
| **App Notes** | Phase set varies by `Scenario.project_type` (new_construction adds pre_construction + construction; conversion adds pre_construction + conversion; value_add adds optional pre_construction + major_renovation; acquisition opt-in adds minor_renovation). Zero-duration phases are dropped so a downstream formula never indexes an empty range. |
| **Excel Formula** | (engine-written integer; consumed by formulas elsewhere) |
| **Excel Notes** | Registered on every workbook that has phase windows: per-project sheet for multi-project scenarios, Assumptions Block E for single-project scenarios. Skipped only for `profile == "proforma"` (engine-only path) or projects with no construction-side phase. |
| **Refs** | [Phase End Month](#phase-end-month), [Phase Duration Months](#phase-duration-months), [Perm Origination Month](#perm-origination-month) |

##### Phase End Month

| Field | Value |
|---|---|
| **Definition** | Last month of a phase, **inclusive** (1-based). A phase of `duration_months=3` starting at month 4 has `end_month=6`. |
| **Named Range** | `p<n>_phase_<phase>_end_month` (e.g. `p1_phase_construction_end_month`) |
| **App Calc/Use** | `build_project_phase_windows` computes `end_month = start_month + duration_months - 1`. |
| **App Notes** | The month *after* a phase ends is `end_month + 1`. That convention is used by `perm_origination_month` to compute the construction-to-perm switchover. |
| **Excel Formula** | (engine-written integer) |
| **Excel Notes** | Used by future construction-to-perm origination formulas — the perm loan's "active from" month equals the last construction-side phase's `end_month + 1`. |
| **Refs** | [Phase Start Month](#phase-start-month), [Perm Origination Month](#perm-origination-month) |

##### Phase Duration Months

| Field | Value |
|---|---|
| **Definition** | Length of a phase in months (positive integer). |
| **Named Range** | `p<n>_phase_<phase>_duration_months` |
| **App Calc/Use** | Equals `PhaseSpec.months` from `_build_phase_plan` — sourced from `OperationalInputs.construction_months` / `lease_up_months` / etc., with milestone-driven overrides via `_apply_milestone_phase_overrides`. |
| **App Notes** | Zero-duration windows are dropped before registration, so every registered duration is ≥ 1. |
| **Excel Formula** | (engine-written integer) |
| **Excel Notes** | Sum across all phases of a project equals [Total Horizon Months](#total-horizon-months). |
| **Refs** | [Phase Start Month](#phase-start-month), [Phase End Month](#phase-end-month) |

##### Perm Origination Month

| Field | Value |
|---|---|
| **Definition** | Absolute month a construction-to-perm loan would convert from its construction tranche to its permanent tranche. Defined as `end_month + 1` of the project's last construction-side phase. |
| **Named Range** | `p<n>_perm_origination_month` |
| **App Calc/Use** | `app/engines/phase_plan.py:perm_origination_month` scans the windows for the last phase whose `period_type` is in `(pre_construction, construction, conversion, major_renovation, minor_renovation)`. |
| **App Notes** | Returns `None` — and the named cell is omitted — for pure-hold projects (`project_type=acquisition` with no opt-in renovation). Perm origination is undefined when there's no construction-side phase. |
| **Excel Formula** | (engine-written integer when present) |
| **Excel Notes** | Future construction-to-perm formulas should reference this cell via `IFERROR(p<n>_perm_origination_month, …)` so pure-hold projects with no cell don't break. |
| **Refs** | [Phase End Month](#phase-end-month), [Annual P&I](#annual-pi-pi-loans-loan-summary), [Debt Service](#debt-service) |

##### Total Horizon Months

| Field | Value |
|---|---|
| **Definition** | Sum of all phase durations for a project — the full modeled timeline including exit month. |
| **Named Range** | `p<n>_total_horizon_months` |
| **App Calc/Use** | `app/engines/phase_plan.py:total_horizon_months` sums `PhaseWindow.duration_months` across the project's windows. Equals the last window's `end_month` (1-based inclusive). |
| **App Notes** | Independent of `Scenario.discount_rate_pct` — purely a timeline length. |
| **Excel Formula** | (engine-written integer) |
| **Excel Notes** | Distinct from `p<n>_timeline_months` (which is the engine's `OperationalOutputs.total_timeline_months`). The two should match in steady state; divergence indicates either a milestone override or a zero-duration phase that was dropped. |
| **Phase 4 hero-KPI consumer** | UW Summary's `s_modeled_duration_months` cell (Total Modeled Duration) now formulas-down to these per-project horizons: single-project = `=IFERROR(p1_total_horizon_months,0)`; multi-project = `=IFERROR(MAX(p1_total_horizon_months,…,pN_total_horizon_months),0)`. LP edits to any phase duration on Assumptions Block E ripple to the hero KPI without re-running the engine. |
| **Refs** | [Phase Duration Months](#phase-duration-months) |

#### F.1.9 Construction-to-Perm Status (per-loan)

First slice of construction-to-perm formula gating. The Debt Schedule's "Construction-to-Perm Status" sub-section emits one row per debt module that funds at least one project with a registered perm-origination month. Each row's two formula cells let an LP see, at a glance, which loans cross the construction-to-perm boundary and whether their active term extends past it.

Rendered by `app/exporters/investor_export.py:_build_c2p_status_block`. Renders for both multi-project and single-project workbooks — single-project gets its `p1_*` phase cells from Assumptions Block E (see §F.1.8 host sheet routing). Skipped only when no debt module funds a project with a construction-side phase (e.g. pure-acquisition scenarios).

##### Loan Perm Origination Month

| Field | Value |
|---|---|
| **Definition** | Per-loan scalar: the month a construction-to-perm loan's permanent tranche would originate. For multi-project loans, the latest perm origination across funded projects (most conservative — "by this month, all funded projects are post-construction"). |
| **Named Range** | `s_loan_<n>_perm_origination_month` |
| **App Calc/Use** | `_build_c2p_status_block` walks the `capital_module_projects` junction to find each loan's funded projects, then writes a formula referencing those projects' `p<idx>_perm_origination_month` cells. |
| **App Notes** | Engine-side, the loan's actual perm switch is governed by `carry.schedule` phases (per `_carry_type_for_phase`). This cell is the formula-side mirror — they should match for well-formed loans, but the engine value is authoritative when they disagree. |
| **Excel Formula** | `=IFERROR(MAX(p<idx1>_perm_origination_month, p<idx2>_perm_origination_month, ...), "")` |
| **Excel Notes** | Wrapped in `IFERROR` so the cell renders blank rather than `#NAME?` when none of the funded projects have a registered perm cell (e.g. all funded projects are pure-hold acquisition). |
| **Refs** | [Perm Origination Month](#perm-origination-month), [Loan Active in Operations](#loan-active-in-operations), [s_loan_n_perm_origination_month](#loan-perm-origination-month) |

##### Loan Active in Operations

| Field | Value |
|---|---|
| **Definition** | Per-loan boolean: TRUE iff the loan's active term extends past perm origination — i.e. the loan's operations-phase carry ever applies in-model. |
| **Named Range** | `s_loan_<n>_active_in_operations` |
| **App Calc/Use** | `_build_c2p_status_block` writes the formula on the same row as the perm-origination cell. Term-months comes from the existing `s_loan_<n>_term_months` cell (registered by `_build_debt_schedule`'s Loan Summary section). |
| **App Notes** | Returns `FALSE` (not `#N/A` or blank) when either input is missing — keeps the section readable in scenarios where one input didn't get a registered cell. |
| **Excel Formula** | `=IFERROR(IF(AND(ISNUMBER(s_loan_n_term_months),ISNUMBER(s_loan_n_perm_origination_month),s_loan_n_term_months>=s_loan_n_perm_origination_month),TRUE,FALSE),FALSE)` |
| **Excel Notes** | `AND(ISNUMBER(...))` guards keep the boolean from returning TRUE when either input is the empty-string `IFERROR` fallback from [Loan Perm Origination Month](#loan-perm-origination-month). |
| **Refs** | [Loan Perm Origination Month](#loan-perm-origination-month), [s_loan_n_perm_origination_month](#loan-perm-origination-month), [s_loan_n_term_months](#loan-summary), [s_loan_n_active_in_operations](#loan-active-in-operations) |

#### F.1.10 Revenue inputs (Assumptions Block F)

Foundation of the engine-to-formula migration for the Pro Forma / Cash Flow / Unit Mix sheets. Every `IncomeStream` record in the scenario gets a row on Assumptions Block F with four user-editable input cells and one computed convenience cell. Downstream sheets can then write `=SUMPRODUCT(s_rev_<slug>_unit_count, s_rev_<slug>_rent_per_unit_monthly, s_rev_<slug>_occupancy_pct)` style formulas instead of baking the numbers in as hardcoded values.

Rendered by `app/exporters/investor_export.py:_build_assumptions_revenue_block`. Slugs come from `_stream_slugs` — lowercased `label`, non-alphanumerics → `_`, collision-resolved with `_2` / `_3` suffixes, blank labels fall back to `stream_<idx>`.

##### Stream Unit Count

| Field | Value |
|---|---|
| **Definition** | Number of units in a revenue stream (typically a unit-type row: studios, 1BR, 2BR, etc.). `None` for fixed-amount streams like parking / laundry. |
| **Named Range** | `s_rev_<slug>_unit_count` |
| **App Calc/Use** | Mirrors `IncomeStream.unit_count` verbatim. Engine multiplies count × rent × occupancy to compute Gross Revenue. |
| **App Notes** | Editable as an input — LP can model add-units scenarios by bumping this cell. Future Pro Forma Gross Revenue formula will SUMPRODUCT across all `s_rev_<slug>_unit_count` cells. |
| **Excel Formula** | (input cell, integer) |
| **Excel Notes** | Empty when the stream is fixed-amount; the Y1 monthly formula falls back to rent-only via `IFERROR`. |
| **Refs** | [Stream Rent Per Unit Monthly](#stream-rent-per-unit-monthly), [Stream Y1 Monthly](#stream-y1-monthly) |

##### Stream Rent Per Unit Monthly

| Field | Value |
|---|---|
| **Definition** | Per-unit monthly rent for a revenue stream, gross of vacancy/concessions. |
| **Named Range** | `s_rev_<slug>_rent_per_unit_monthly` |
| **App Calc/Use** | Mirrors `IncomeStream.amount_per_unit_monthly`. |
| **App Notes** | LP-editable input. Pro Forma Gross Revenue Y1 formula will multiply by unit_count × occupancy × 12. |
| **Excel Formula** | (input cell) |
| **Excel Notes** | For fixed-amount streams (parking, laundry, billboard), the unit_count cell is empty and this cell holds the full monthly amount. The Y1 monthly formula's `IFERROR` branch handles that case. |
| **Refs** | [Stream Unit Count](#stream-unit-count), [Stream Y1 Monthly](#stream-y1-monthly) |

##### Stream Occupancy Pct

| Field | Value |
|---|---|
| **Definition** | Stabilized occupancy percentage applied to this stream's gross revenue. |
| **Named Range** | `s_rev_<slug>_occupancy_pct` |
| **App Calc/Use** | Mirrors `IncomeStream.stabilized_occupancy_pct`. Engine applies during stabilized periods; lease-up phases use a ramp instead. |
| **App Notes** | Stored as 0–100 (e.g. 95.0). Excel display format is `0.0%`. |
| **Excel Formula** | (input cell, 0–100) |
| **Excel Notes** | Stream-level granularity lets LPs model unit-type-specific vacancy (e.g. studios 90%, 2BR 95%). |
| **Refs** | [Stream Unit Count](#stream-unit-count), [Stream Y1 Monthly](#stream-y1-monthly) |

##### Stream Escalation Pct

| Field | Value |
|---|---|
| **Definition** | Annual rent escalation rate for this stream. Applied Y2+ in Pro Forma; Y1 = stabilized rent. |
| **Named Range** | `s_rev_<slug>_escalation_pct` |
| **App Calc/Use** | Mirrors `IncomeStream.escalation_rate_pct_annual`. |
| **App Notes** | Per-stream so LP can model differential escalation (e.g. retail CAM 0%, residential 3%). Future Pro Forma Y2+ revenue formula: `=Y1 * (1 + s_rev_<slug>_escalation_pct/100)^(year-1)`. |
| **Excel Formula** | (input cell, 0–100) |
| **Excel Notes** | Distinct from scenario-level `s_revenue_growth_rate` which is the engine's default fallback when stream-level escalation is 0. |
| **Refs** | [Stream Rent Per Unit Monthly](#stream-rent-per-unit-monthly) |

##### Stream Y1 Monthly

| Field | Value |
|---|---|
| **Definition** | Computed Y1 stabilized monthly revenue for the stream — gives an LP an at-a-glance sanity check on each line. |
| **Named Range** | `s_rev_<slug>_y1_monthly` |
| **App Calc/Use** | Formula cell, not stored on `IncomeStream`. Recomputes live when any of the three input cells change. |
| **App Notes** | Future Pro Forma Gross Revenue Y1 will be `=SUMPRODUCT` across `s_rev_*_y1_monthly * 12` (annualizing). |
| **Excel Formula** | `=IFERROR(s_rev_1_unit_count*s_rev_1_rent_per_unit_monthly*s_rev_1_occupancy_pct, s_rev_1_rent_per_unit_monthly*s_rev_1_occupancy_pct)` |
| **Excel Notes** | `IFERROR` branch covers fixed-amount streams (no unit_count) — falls back to rent × occupancy. The `_1_` index in the formula is illustrative; the real slug embeds the stream label (e.g. `s_rev_1br_units_unit_count`). |
| **Refs** | [Stream Unit Count](#stream-unit-count), [Stream Rent Per Unit Monthly](#stream-rent-per-unit-monthly), [Stream Occupancy Pct](#stream-occupancy-pct), [s_rev_n_unit_count](#stream-unit-count), [s_rev_n_rent_per_unit_monthly](#stream-rent-per-unit-monthly), [s_rev_n_occupancy_pct](#stream-occupancy-pct) |

#### F.1.11 Operating Expense inputs (Assumptions Block G)

Companion to §F.1.10 for OpEx side of the model. Every `OperatingExpenseLine` record in the scenario gets a row on Assumptions Block G with two user-editable input cells and one computed convenience cell. Downstream Pro Forma OpEx rows can reference these instead of hardcoding annual amounts.

Rendered by `app/exporters/investor_export.py:_build_assumptions_opex_block`. Slugs come from `_opex_slugs` (same algorithm as `_stream_slugs`, blank labels fall back to `opex_<idx>`).

##### OpEx Annual

| Field | Value |
|---|---|
| **Definition** | Y1 annual operating expense for an OpEx line (property mgmt, insurance, taxes, etc.). |
| **Named Range** | `s_opex_<slug>_annual` |
| **App Calc/Use** | Mirrors `OperatingExpenseLine.annual_amount`. |
| **App Notes** | LP-editable input. Future Pro Forma OpEx row Y1 formula: `=s_opex_<slug>_annual`. Y2+ applies escalation. |
| **Excel Formula** | (input cell) |
| **Excel Notes** | Total OpEx will be `=SUM(s_opex_*_annual)` on the Pro Forma sheet once that conversion lands. |
| **Refs** | [OpEx Escalation Pct](#opex-escalation-pct), [OpEx Monthly](#opex-monthly) |

##### OpEx Escalation Pct

| Field | Value |
|---|---|
| **Definition** | Annual escalation rate for this OpEx line. Applied Y2+; Y1 = `s_opex_<slug>_annual`. |
| **Named Range** | `s_opex_<slug>_escalation_pct` |
| **App Calc/Use** | Mirrors `OperatingExpenseLine.escalation_rate_pct_annual`. |
| **App Notes** | Per-line so LP can model contracted-rate lines (e.g. property tax CPI-capped at 2%) separately from market-driven lines (insurance +5%/yr). |
| **Excel Formula** | (input cell, 0–100) |
| **Excel Notes** | Distinct from scenario-level `s_opex_growth_rate` which the engine uses as default when this is 0. |
| **Refs** | [OpEx Annual](#opex-annual) |

##### OpEx Monthly

| Field | Value |
|---|---|
| **Definition** | Computed Y1 monthly OpEx for the line — convenience cell for LPs reviewing per-line burden vs. revenue. |
| **Named Range** | `s_opex_<slug>_monthly` |
| **App Calc/Use** | Formula cell. Updates live with `s_opex_<slug>_annual`. |
| **App Notes** | Not used by the engine — pure display convenience. Pro Forma uses annual figures. |
| **Excel Formula** | `=s_opex_1_annual/12` |
| **Excel Notes** | Reciprocal of the Pro Forma's annual-display convention. The `_1_` index is illustrative; real slug embeds the line label (e.g. `s_opex_property_management_annual`). |
| **Refs** | [OpEx Annual](#opex-annual), [s_opex_n_annual](#opex-annual) |

### F.2 Defined-name conventions

- `s_*` — single scalar (one cell). E.g. `s_combined_noi`, `s_revenue_growth_rate`, `s_loan_3_annual_pi`.
- `p<n>_*` — per-project scalar. E.g. `p1_noi_stabilized`.
- `r_*` — multi-cell row range. E.g. `r_uw_cf_levered` is the annual Levered Cash Flow row on Underwriting Cash Flow.

A test (`tests/exporters/test_investor_export.py::test_every_named_range_traces_to_doc_entry`) enforces that every `s_*` name on the workbook either maps to a metric documented elsewhere in this file or is explicitly listed as a non-metric input (assumption cell, header, etc.).

### F.3 Parity with the engine

Excel formulas only have to *track* engine values, not match bit-for-bit:

- **Engine-side** is Decimal arithmetic with monthly periods and day-precise interest accrual (see §1–§6).
- **Workbook-side** is Excel float arithmetic over annual columns. Excel's `IRR()` runs annual intervals; the engine's `combined_irr_pct` runs monthly XIRR.

Parity tests in `tests/exporters/test_formula_parity_*.py` recalc workbooks via Excel COM (Windows) or LibreOffice headless and assert Excel-evaluated values match engine values within tolerances calibrated per metric (e.g. ±0.5pp for IRR, ±$1 for $-denominated cells, ±0.5x for EM). Tests skip when no recalc backend is available.

### F.4 Graceful degradation

- Every conditional metric is wrapped in `IFERROR(...,"")` or `IFERROR(...,0)` so missing inputs render as empty (or 0) rather than `#DIV/0!` / `#NUM!`.
- The Debt Schedule's "Notes" block conditionally emits disclosure rows only when the underlying state is present (DSCR-capped sizing, interest-reserve carry, PIK carry). Vanilla perm-debt deals see no Notes section.
- The Assumptions sheet's Block A includes editable `s_anchor_date` so the LP can overlay a reporting calendar on the relative Y0/Y1/Y2 grid without rebuilding the model.

---

## Appendix G: Bank-Account Solvency Proof (May 2026)

The cashflow engine sizes reserves (OR, IR, LUR) as static lump sums funded at Close. The bank-account proof is a separate *period-level simulation* that walks the bank balance month by month from Day 0 (Close) through Stabilization Start and verifies it never dips below the operating reserve floor. A violation is engine-side proof that reserve sizing is wrong — it is not a user-facing warning.

### G.1 Two simulators, one continuous window

Pre-existing engines each cover half the window:

- `app/engines/draw_schedule.py` — `_simulate_cash_balance()` produces `MonthlyCashFlow` rows for **Close → CO** (construction)
- `app/engines/cashflow.py` — `_compute_project_cashflow()` produces `CashFlow` rows for **CO → exit** (operations, including lease-up)

`extract_full_window_proof(...)` in `app/engines/bank_account_extractor.py` stitches the two into one continuous timeline:

1. **Opening cash** = sum of `first_day` reserve UseLines (OR + IR + LUR + Cash Flow Support Reserve, etc.).
2. **Segment 1 — construction** = `MonthlyCashFlow` rows from `draw_schedule.py`.
3. **Segment 2 — lease-up** = `CashFlow` rows from `cashflow.py` filtered to months between CO and Stabilization Start.
4. **Overlap resolution** = construction wins on any overlap month (the draw-schedule simulator owns construction).

`_RESERVE_LABELS` in `bank_account_extractor.py` is the canonical set of reserve labels recognized at Close — "Operating Reserve", "Interest Reserve", "Lease-Up Reserve", "Cash Flow Support Reserve". Renaming a reserve elsewhere without updating this set will break the opening-cash invariant.

### G.2 `funded_carry` flag on `SourceDef`

The draw schedule engine has two interest models:

| Model | When | Behavior |
|---|---|---|
| Self-referential capitalized | `funded_carry=False` and `annual_interest_rate > 0` | `D = (uses + payoff + B × (F−1)) / (2−F)` where `F = (1+r)^n` — compound interest version. For `n=1` (monthly draws) this is algebraically identical to the prior simple-interest formula `(uses + B×r)/(1−r)`. Implemented in `compound_draw_sizing()` in `app/engines/period_engine.py`. |
| Funded-carry pool | `funded_carry=True` | Carry on this loan is paid from a pre-funded Interest Reserve UseLine. Draw = `uses + payoff` only; `carry_cost = 0` to avoid double-counting (the IR pool already drained for the same interest). |

`app/api/routers/ui.py` builds `SourceDef.funded_carry = True` when the `CapitalModule.carry.schedule` contains a phase with `carry_type="interest_reserve"`. Without this flag, the draw schedule and the cashflow engine would charge the same loan interest twice (once via capitalization in `_calc_source_draws`, once via the IR pool drawdown in `_compute_project_cashflow`).

### G.3 Cash Flow Support Reserve — auto-emitted gap-filler

When `extract_full_window_proof` detects a month where `cash_balance < required_reserve`, cashflow auto-emits a new `UseLine` labeled **"Cash Flow Support Reserve"** sized to plug the largest shortfall. It is:

- `timing_type="first_day"` — funded at Close
- `cost_category="soft"` — appears in Sources & Uses under soft costs
- Included in `_RESERVE_LABELS` so the next sizing iteration counts it toward opening cash

The compute loop in `app/api/routers/models.py` re-runs draw schedule + cashflow up to `MAX_ITERATIONS` times. Each iteration recomputes `construction_monthly` from the latest draw schedule and passes it to `compute_cash_flows`. Convergence: once Cash Flow Support is in opening cash, the next pass either eliminates the shortfall (gap → 0) or stabilizes at a fixed reserve amount within tolerance. If `_RESERVE_LABELS` omitted "Cash Flow Support Reserve", the loop would spin at the same shortfall forever — the emitted reserve wouldn't be recognized as opening cash.

### G.3.1 Deferred Dev Fee paydown outflows

The bank-account proof's outflow formula was `operating_expenses + debt_service` per row through 2026-06-02. After Float Earnings Phase B shipped, the CF waterfall began routing operating NCF to a `deferred_developer_fee` tier, draining real cash from the operating account that the proof was blind to. This caused the Cash Flow Support Reserve to undersize on any deal with a deferred Dev Fee balance.

Fix (2026-06-02): each `_run_bank_account_proof` call now receives a `dev_fee_paydowns_by_period` dict — period → paydown amount from the prior iteration's waterfall — and the extractor folds those into `outflows[m]` alongside opex + debt service. The convergence loop in `compute_model_cashflows` runs the waterfall **inside** the loop (previously after) and trips `needs_recompute=True` whenever the deferred Dev Fee paydown total shifts by more than $1 between passes, so CFS sizing converges against a stable schedule.

- Iteration 0: `dev_fee_balance_series` is empty on `OperationalOutputs`; proof sees no paydowns → matches pre-Phase-B behavior on new deals.
- Iteration 1+: prior iteration's series populates the paydown dict; proof outflows reflect cash leaving the operating account into the dev fee creditor.
- Only `paydown_from_waterfall` counts. `paydown_from_float_topup` is funded by a float source (not the operating account) and is invariant-preserving (Appendix I.2 — float earnings never appear in `effective_gross_income` either).

### G.4 Per-scenario allowlist

The bank-account reserve emission is gated by `_bank_account_reserve_active_for(scenario_id)` in `cashflow.py`:

```
_BANK_ACCOUNT_RESERVE_ALLOWED_SCENARIOS = set from env BANK_ACCOUNT_RESERVE_ALLOWED_SCENARIOS
_BANK_ACCOUNT_RESERVE_ENABLED          = global on/off (BANK_ACCOUNT_RESERVE_ENABLED env)
```

Precedence:

1. If the allowlist env var is non-empty → only scenarios in the list have reserve emission active. All others fall back to the legacy `extract_operating_proof_window` path.
2. If the allowlist is empty → the global flag applies to every scenario.

This is a pilot-mode lever: ship to one production deal first, verify, then either remove the allowlist (everyone gets the feature) or expand it.

### G.5 Files involved

| File | Role |
|---|---|
| `app/engines/period_engine.py` | `run_period_engine()`, `compound_draw_sizing()`, `compound_accrual()` — canonical carry math for all 4 carry types; IR pool tracking; bank balance accounting |
| `app/engines/bank_account_extractor.py` | `extract_full_window_proof`, `_RESERVE_LABELS` |
| `app/engines/draw_schedule.py` | `_simulate_cash_balance`, `_calc_source_draws`, `SourceDef.funded_carry` |
| `app/engines/cashflow.py` | `_run_bank_account_proof`, `_bank_account_reserve_active_for`, Cash Flow Support emission |
| `app/api/routers/ui.py` | Builds `SourceDef.funded_carry` from `CapitalModule.carry.schedule` |
| `app/api/routers/models.py` | `/compute` iteration loop wiring `construction_monthly` between engines |

### G.6 Convergence invariants (test coverage)

- `tests/engines/test_bank_account_extractor.py` — opening-cash recognition, segment ordering, overlap resolution
- `tests/engines/test_draw_schedule.py::test_funded_carry_skips_self_referential_capitalization` — `funded_carry=True` does not capitalize
- `tests/engines/test_draw_schedule.py::test_funded_carry_vs_capitalized_diverge_by_expected_amount` — divergence equals expected interest pool
- `tests/engines/test_cashflow_bank_account_wiring.py` — allowlist gate (4 tests covering all precedence cases)
- `tests/engines/test_bank_account_extractor.py::test_cash_flow_support_reserve_counts_toward_opening_cash` — convergence regression

## Appendix H: Multi-Source Developer Fee (June 2026)

Pre-0103, Developer Fee was a single auto-managed UseLine
(`is_auto_dev_fee=True`) with one global basis and one global %. In any deal
with mixed capital — regulated/affordable Sources (LIHTC, tax-exempt bonds,
HUD, HFA) alongside private debt or equity — each Source imposes a
different rule about what TPC means and what fee it allows. The binding fee
is the minimum allowable across all Sources, and which Source binds drives
sponsor economics and deferred-fee sizing.

Migration 0103 added the four-layer configuration hierarchy that supports
this, the multi-source engine that computes per-Vehicle allowances and
binding constraint, the funded-vs-deferred split, the milestone-based
release schedule, and three acquisition treatments.

### H.1 Four-layer configuration

| Layer | Source of truth |
|---|---|
| Org/User defaults | `org_settings` / `user_settings` keyed by deal type — `dev_fee_pct_*`, `dev_fee_basis_*`, `dev_fee_acquisition_treatment_*`, `dev_fee_acquisition_pct_*`, `acquisition_fee_pct_*`, `dev_fee_final_holdback_pct_*`, `dev_fee_milestone_weights_*` |
| Source Vehicle preset | `source_vehicles.fee_terms` JSONB — per-preset rule edited at `/settings/vehicles`. Empty dict = no cap from this preset (renamed from per-Type defaults table; migration 0105 dropped `capital_vehicle_fee_defaults`) |
| Source Vehicle row (`CapitalModule`) | `fee_terms` JSONB + `fee_terms_inherited_from_type` flag — when True, engine reads `SourceVehicle.fee_terms` from the preset referenced by `source_vehicle_id`; when False, the instance `fee_terms` is the source of truth |
| Per-(UseLine × Vehicle) custom-Use override | `use_line_source_fee_basis` join table — required for any UseLine whose `cost_category` is outside the eight standard categories |

### H.2 Standard cost categories

Used by `basis_exclusions` on each Vehicle's `fee_terms`:

`acquisition`, `hard_costs`, `soft_costs`, `financing_fees`,
`interest_reserve`, `operating_reserves`, `developer_overhead`,
`consulting_fees`.

UseLines outside this set are treated as custom Uses. The engine reads
`use_line_source_fee_basis` for `(use_line_id, capital_module_id)` to
decide inclusion; if missing, the pair is flagged as a pending decision
and conservatively excluded from the basis.

### H.3 Binding constraint reducer

For each Vehicle with at least one cap set on `fee_terms`
(`max_pct` / `per_unit_cap` / `absolute_cap`):

`allowable = min(max_pct × basis, per_unit_cap × units, absolute_cap)`

where `basis = sum(use_lines included by this Vehicle's basis_exclusions
and use_line_source_fee_basis)`.

Engine takes the minimum allowable across all constrained Vehicles. This
is the binding cap. **Elected fee always wins**: the engine never
overrides the user-elected fee. Overage is reported in
`UseLine.dev_fee_binding_context` and surfaced in the explainer modal.

### H.4 Funded vs deferred split

After the elected fee is fixed, the engine allocates greedily to
constrained Vehicles (capacity-ordered) up to each Vehicle's allowance.
Remainder = deferred. V1 keeps the full elected fee on the auto Dev Fee
UseLine `amount` (today's Uses treatment); the funded/deferred split is
reported in the binding context for display and is **informational only**
in the cashflow engine today. Subordinate-claim operating-cash
consumption of the deferred portion is a Phase 3b follow-up.

### H.5 Milestone release schedule

`UseLine.dev_fee_release_schedule` JSONB carries
`{weights: [{milestone_id, weight}], final_holdback: {milestone_id, pct}}`.
Weight sum + holdback pct must equal 1.0. Engine emits a list of dated
receipts (`milestone_id`, `date`, `weight`, `amount`) in the binding
context. Holdback releases at its assigned milestone.

### H.6 Acquisition treatments

`UseLine.dev_fee_acquisition_treatment` ∈ `{excluded, split_rate,
separate_fee, NULL}`.

| Treatment | Behavior |
|---|---|
| `excluded` | Standard Dev Fee on TPC excl. acquisition. No Acquisition Fee row. |
| `split_rate` | Single auto Dev Fee row with basis partitioned: `dev_fee_pct × construction_basis + dev_fee_acquisition_pct × acquisition_basis`. Each half honors per-Vehicle `basis_exclusions`. |
| `separate_fee` | Standard Dev Fee on construction basis PLUS a parallel auto Acquisition Fee UseLine (`is_auto_acquisition_fee=True`) where `amount = acquisition_fee_pct × purchase_price`. Both fees independently capped by each Vehicle's `fee_terms`; results stored side by side in `dev_fee_binding_context.acquisition_fee_context`. |
| `NULL` (legacy) | Pre-0103 behavior — `tpc_excl_self` sums ALL non-self UseLines, including acquisition. Preserved for backward compat. |

Defaults by deal type: `acquisition → separate_fee`,
`value_add → split_rate`, `conversion → excluded`,
`new_construction → excluded`.

### H.7 Structural diff signal

Each compute hashes `(sorted CapitalModule IDs, sorted non-auto UseLine
IDs)` and writes it to
`UseLine.dev_fee_binding_context.last_compute_signature`. Next compute
compares against the previous signature; mismatch sets
`structural_diff_detected=True`. The UI auto-opens the explainer modal
with a warning banner so the user reconfirms the fee treatment when the
capital stack shape changes. Pure amount edits do not trip the diff.

### H.8 Files involved

| File | Role |
|---|---|
| `alembic/versions/0103_dev_fee_multi_source.py` | Schema migration |
| `app/models/capital.py` | `CapitalModule.fee_terms`, `UseLineSourceFeeBasis` |
| `app/models/source_vehicle.py` | `SourceVehicle.fee_terms` (per-preset Dev Fee rule; migration 0105) |
| `app/models/deal.py` | `UseLine.dev_fee_release_schedule`, `dev_fee_binding_context`, `is_auto_acquisition_fee`, `dev_fee_acquisition_treatment`, `dev_fee_acquisition_pct`, `acquisition_fee_pct` |
| `app/schemas/capital.py` | `CapitalFeeTermsSchema` |
| `app/schemas/deal.py` | `DevFeeReleaseScheduleSchema`, `DevFeeBindingContextSchema`, `UseLineSourceFeeBasisSchema` |
| `app/engines/dev_fee.py` | Multi-source pipeline (binding constraint, funded/deferred, release, structural diff) |
| `app/engines/cashflow.py` | Call site passes `modules`, `org_id`, `milestone_dates` |
| `app/settings/defaults.py` + `resolver.py` | 20 new keys + extended `resolve_dev_fee_config` |
| `app/api/routers/capital.py` | `/models/{id}/use-line-source-fee-basis` CRUD |
| `app/api/routers/ui.py` | `GET /ui/models/{id}/dev-fee/explainer` HTMX route |
| `app/templates/partials/dev_fee_explainer_modal.html` | Explainer modal partial |
| `tests/engines/test_dev_fee_multi_source.py` | 12 priority tests |

### H.9 Phase 2 / follow-up scope

**Shipped — June 2026 (Float Earnings Phase B, simplified):** all float
earnings route directly to the GP/LP profit waterfall as a lump sum
at the user-chosen **Waterfall Milestone**. The `deferred_developer_fee`
tier (auto-seeded between `debt_service` and `residual` when the DDF
capital module amount > 0) consumes operating cash period-by-period
up to the remaining DDF balance. Found-money injection into `available_cash`
at the milestone period then flows through normal tier order
(debt service → DDF → residual equity split). The split-routing model
(dev_fee_split_pct / debt_paydown_split_pct) was removed in favour of
this single clean path. See Appendix I.4 and I.5.

Still pending:

- Source Vehicle drawer "Developer Fee Rule" section with inheritance
  affordance.
- UseLine drawer "Release Schedule" editor.
- Capital Vehicle Defaults Org settings page.
- Risk / tax layers and construction-fund reinvestment module.

## Appendix I — Float Earnings on Day-1 Draws

Some capital sources — most importantly tax-exempt construction bonds — are required to draw 100% of proceeds at closing. The cash sits in an account earning Treasury yield until it is paid out against construction Uses. Appendix I documents how the engine models that interest income, the routes it can take to benefit the deal, and the conservative invariants that protect reserve sizing.

### I.1 Source taxonomy and trigger

A new capital `vehicle_type` value, `float_earnings`, represents this kind of source. It is distinct from `debt`, `equity`, `forgivable_loan`, and `grant`, and is intentionally invisible to the waterfall (`waterfall.py` filters only `debt` vs `equity`) and to the source-routing gap-fill solver (`source_routing.eligible_sources_for_use` excludes it).

Two flags on the **parent** source gate float-earnings computation:

- `source.draw_type == "fully_drawn"` — parent must lump-draw on Day 1
- `source.balance_earns_interest == True` — explicit opt-in by the user

When either is missing, the engine pauses the child float-earnings source and surfaces a warning rather than silently producing zero. The child source remains in the Sources table with its config intact; it resumes earnings on the next recompute when the parent is fixed.

### I.2 Closed-form balance schedule

For a parent source with principal `P` drawn day 1, construction over `N` months, and annual user-entered yield `y%`, the engine computes a per-month series and the closed-form total:

```
balance(t)   = P × (1 − t/N)              for t in 0..N    (linear depletion)
earnings(t)  = balance(t-1) × y/100/12    for t in 1..N
total        = Σ earnings(t)
             = P × y/100/12 × (N + 1)/2
```

Why linear depletion: it matches the `linear` draw-schedule convention already used by the interest-reserve sizer (`_draw_schedule_for("interest_reserve", "draw_down") == "linear"`). Float earnings then become a natural mirror image of IR on a lump-drawn loan.

Why earnings are not reinvested into the balance: the dollars are committed downstream (to debt paydown or developer-fee top-up via the user-entered split) and never return to the parent's drawn balance. Compounding would overstate income.

Implementation lives in `app/engines/float_earnings.py:compute_balance_schedule`.

### I.3 Reserve-sizing invariant

Float earnings DO NOT shrink any reserve. Specifically:

- **Interest Reserve** — sized by `_auto_size_debt_modules()` which operates algebraically on principal × rate × duration. Float earnings run *after* this call and never reach the sizer's inputs.
- **Operating Reserve / Lease-Up Reserve / Cash Flow Support Reserve** — sized by their respective extractors (`bank_account_extractor`, `_run_bank_account_proof`) which see the cashflow row stream and reserve UseLines. Float earnings never appear as cashflow inflows.

Reason for the conservative position: T-bond secondary-market sale timing cannot be reliably aligned to construction draw needs. Treating the income as freely available would allow the engine to under-size reserves on the optimistic assumption that the bonds clear when the project needs cash. The sponsor would be exposed if that timing slipped.

### I.4 Application path — "Found Money"

All float earnings route to the GP/LP profit waterfall as a **lump sum** at the
user-chosen **Waterfall Milestone**. No split routing, no direct debt paydown,
no direct Dev Fee balance reduction.

Mechanics:
1. `cashflow.py` resolves the waterfall milestone to a period number and writes it into
   `float_earnings_series["found_money_periods"]` (a `{str(period): amount}` dict).
2. In the waterfall loop, at that period the lump sum is added to `available_cash`.
3. Normal tier order applies: debt service is paid first, then DDF balance (if any),
   then residual equity split. Float earnings are not ring-fenced — they flow wherever
   the deal's tier ordering directs them.

The engine does **not** surface a separate `capital_event` line item for the injection;
the amount becomes visible through the DDF Recov. column (if the DDF tier consumes it)
or the equity distribution rows in the waterfall report.

**Backward compat:** the legacy `paydown_milestone_id` key on `CapitalSourceSchema` is
still read if `waterfall_milestone_id` is absent, so existing source JSONB rows continue
to work without re-save.

### I.5 Persistence and UI surface

Per-source results are persisted on `OperationalOutputs.float_earnings_series` (JSONB):

```json
{
  "sources": [{
    "float_source_id": "...",
    "parent_module_id": "...",
    "total_earnings": 302017.47,
    "waterfall_milestone_id": "...",
    "schedule": [{"period": 1, "opening_balance": 10000000, "monthly_earnings": 41666.67, "closing_balance": 9000000}],
    "warnings": []
  }],
  "found_money_periods": {"43": 302017.47},
  "warnings": []
}
```

`found_money_periods` is a `{str(period): amount}` dict pre-resolved by `cashflow.py`
so the waterfall loop can inject lump sums with a dict lookup rather than re-loading
milestones. It is the only key the waterfall reads from this blob.

The computed `total_earnings` is also written back to the float_earnings capital
module's `source["amount"]` at the end of each cashflow compute, so the S&U panel
shows the Found Money dollar amount without re-running the engine.

`OperationalOutputs.dev_fee_balance_series` tracks the DDF repayment schedule:

```json
{
  "opening_at_close": "628195.68",
  "fully_paid_period": 40,
  "total_paid": "628195.68",
  "remaining_at_horizon": "0",
  "periods": [{
    "period": 1,
    "opening_balance": "628195.68",
    "paydown_from_waterfall": "12563.91",
    "paydown_from_float_topup": "0",
    "closing_balance": "615631.77"
  }, ...]
}
```

`opening_at_close` = the DDF **capital module** `source["amount"]` (what was contributed
as a source and needs to be repaid), not the total developer fee deferred.

Both columns follow `bank_account_proof` (Appendix G.4) semantics: always written so
stale data clears, None when no relevant source/module exists.

### I.6 Files involved

| File | Role |
|---|---|
| `app/engines/float_earnings.py` | Validation gate, closed-form balance math, scenario orchestrator. `FloatEarningsResult` carries `float_source_id`, `parent_module_id`, `total_earnings`, `waterfall_milestone_id`, `schedule`, `warnings` — no split fields. |
| `app/engines/dev_fee_balance.py` | Pure-function DDF balance schedule; `compute_deferred_balance_schedule` + `serialize_balance_result`. `float_topups_by_period` param accepted but passed as `{}` — found money no longer reduces the DDF balance directly. |
| `app/engines/cashflow.py` | Pre-resolves `found_money_periods` dict from float results; writes `total_earnings` back to each float module's `source["amount"]`; runs `_auto_size_ddf_module()` after `_auto_size_debt_modules()`. |
| `app/engines/waterfall.py` | DDF tier auto-seeded when DDF capital module amount > 0 (reads `_read_deferred_dev_fee_at_close` from the module, not the use line). Found money injected into `available_cash` at the milestone period. Persists `dev_fee_balance_series` on `OperationalOutputs`. |
| `app/engines/source_routing.py` | Excludes `float_earnings` from Use-funding eligibility. |
| `app/models/capital.py` | `VehicleType.float_earnings`; `VehicleType.deferred_developer_fee`; `WaterfallTierType.deferred_developer_fee` |
| `app/models/cashflow.py` | `OperationalOutputs.float_earnings_series` and `dev_fee_balance_series` JSON columns |
| `app/schemas/capital.py` | `CapitalSourceSchema` float-earnings fields (parent ref, yield, `waterfall_milestone_id`). `CapitalExitSchema.trigger` is optional (`str \| None = None`) to accommodate DDF modules whose `exit_terms` lack a trigger. |
| `app/api/routers/ui.py` | CF routes load `dev_fee_balance_series` into template context as `ddf_recovery_by_period` + `ddf_balance_by_period`. Float source save handler writes `waterfall_milestone_id` (reads legacy `paydown_milestone_id` for compat). |
| `app/templates/partials/model_builder_line_form.html` | Float-earnings form: parent module picker, yield %, Waterfall Milestone picker. Split % fields removed. Developer Fee Rule section hidden for `float_earnings` vehicle type. |
| `app/templates/partials/model_builder_panel.html` | CF table has DDF Recov. (orange, period paydown from waterfall) and DDF Bal. (remaining balance) columns. S&U "Found Money" summary block shows total earnings → GP/LP Profit Waterfall. |
| `app/templates/partials/vehicle_form.html` | Developer Fee Rule section hidden for `float_earnings` vehicle type. |
| `alembic/versions/0104_operational_outputs_float_earnings.py` | Migration for `float_earnings_series` column |
| `alembic/versions/0107_dev_fee_balance_series.py` | Migration for `dev_fee_balance_series` column |
| `tests/engines/test_float_earnings.py` | Unit coverage |
| `tests/engines/test_dev_fee_balance.py` | Unit tests for balance schedule helper |
| `tests/engines/test_waterfall.py` | Integration tests for DDF tier consumption + auto-seed |

### I.7 Known limitations

| Limitation | Resolution |
|---|---|
| Yield curve is a single user-entered annual % | Future: scheduled fetch of Treasury curve with per-month yield indexing |
| Multi-project scenarios: DDF balance reads from the default-project OO row only (`Scenario.operational_outputs` is `uselist=False`); matches same limitation in `_apply_levered_metrics` | Phase 2f+ multi-project waterfall work |
| Integration + E2E tests for the float-earnings Waterfall Milestone form field are still pending | Follow-up: API integration test for capital-module CRUD + E2E flow |
| DDF opening balance is the DDF capital module amount, not the total deferred dev fee — if the developer deferred more than the gap-fill amount, the excess dev fee recovery is not modeled in the DDF balance schedule | Phase 2+ full dev-fee payout tracking |

### I.8 DDF auto-sizing

When a `deferred_developer_fee` capital module has `source.auto_size == true`, the
engine automatically sets its `source["amount"]` to fill the residual Sources = Uses
gap after all debt modules have been sized:

```
ddf_amount = min(gap, dev_fee_total)
gap        = max(0, uses_total − other_sources_total)
dev_fee_total = Σ use_lines where is_auto_dev_fee or is_auto_acquisition_fee
```

`other_sources_total` excludes `deferred_developer_fee` and `float_earnings` vehicle
types. The DDF is intentionally last-resort: `_auto_size_ddf_module()` runs in
`cashflow.py` after `_auto_size_debt_modules()` completes.

This means:
- If debt auto-sizing already closes the gap, DDF amount → $0 (still in stack, just
  draws nothing).
- If a gap remains, DDF fills it up to the available developer fee pool.
- `float_earnings` is excluded from Sources total so found-money never inflates the
  apparent Sources balance and masks a real gap.

The Gap Adjustment slider (`/models/{id}/gap-adjust`) operates on top of this: it
adds/removes a phantom use line to shift the Sources = Uses balance after
auto-sizing has run.

