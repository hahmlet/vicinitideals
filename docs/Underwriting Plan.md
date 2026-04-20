# Multi-Project Underwriting — Data, Math & Logic Schema

## Context

Today `Scenario` permits 1:N `Projects` structurally, but the engine collapses to the first one ([app/engines/cashflow.py:68](../app/engines/cashflow.py#L68)). `CapitalModule` / `DrawSource` / `WaterfallTier` are `scenario_id`-scoped and treated as if one project exists. `UseLine` / `IncomeStream` / `OpExLine` / `OperationalInputs` / `Milestone` are already `project_id`-scoped.

The real need: an investor often closes one debt package that funds multiple projects. Each project must still stand on its own merits — its own timeline, uses, draws, carry, cashflow, waterfall, IRR. The combined view is what gets shown to the lender / committee.

## Terminology (normalized)

- **Deal** — top-level investment thesis (unchanged).
- **Deal Variant / Scenario** — one financial plan for a Deal, containing N Projects and shared Sources. User-facing term is "Variant"; DB entity is `Scenario`.
- **Project** — individual development effort. Has its own timeline, uses, sources, draws, cashflow, waterfall, IRR. Computed independently.
- **Source** — user-facing name for `CapitalModule`. A Source has an identity (lender, rate, carry type). One Source can attach to 1+ Projects.
- **Underwriting** — the rolled-up, computed view of a Scenario: combined timeline, combined draw schedule, combined cashflow, combined Source package (with shared Sources deduped), combined IRR, joined waterfall table. Derived from per-project outputs. 1:1 with Scenario. Each Variant has its own Underwriting.

## Key Architectural Principle

**Cross-project math is deferred, but cross-project timing is not.** Each project's math runs independently using the existing engine. The Underwriting layer aggregates afterward.

The one thing that must resolve before per-project math: **relational timelines**. A user may anchor Project 2's acquisition to Project 1's close (+ N months). Moving Project 1 moves Project 2. So project start dates are resolved at the Underwriting layer first (topological sort over trigger chains), then each project computes with its resolved dates, then outputs aggregate. The engine itself stays single-project; only date resolution is cross-project.

## Current State (relevant facts)

| Concern | Scope today | File |
|---|---|---|
| Engine picks default project | `scenario.projects[0]` | [app/engines/cashflow.py:68](../app/engines/cashflow.py#L68) |
| CapitalModule | `scenario_id` | [app/models/capital.py:43](../app/models/capital.py#L43) |
| DrawSource | `scenario_id`, optional `capital_module_id` | [app/models/capital.py:146](../app/models/capital.py#L146) |
| WaterfallTier / Result | `scenario_id` | [app/models/capital.py:79](../app/models/capital.py#L79), [:114](../app/models/capital.py#L114) |
| UseLine / Income / OpEx / OpInputs / Milestone | `project_id` | [app/models/deal.py](../app/models/deal.py), [app/models/milestone.py](../app/models/milestone.py) |
| `_auto_size_debt_modules` | single-project uses pool | [app/engines/cashflow.py:1001](../app/engines/cashflow.py#L1001) |
| `_loan_pre_op_months` | windowed per-module, ready | [app/engines/cashflow.py:1053](../app/engines/cashflow.py#L1053) |
| Reserve use lines injected on default project | IR / CI / Lease-Up / Acq Interest | [app/engines/cashflow.py:1574](../app/engines/cashflow.py#L1574), [:1760](../app/engines/cashflow.py#L1760) |

---

## Proposed Data Model

### 1. Source (CapitalModule) identity persists at the Scenario level

`CapitalModule` stays `scenario_id`-scoped. It holds the **shared contract identity** — lender, rate, amortization, carry_type, exit_terms. Everything that's truly the same across projects because it's the same contract.

**Move to junction (below):** per-project amount, per-project active window, per-project sizing flag.

### 2. New `capital_module_projects` junction with per-project terms

Semantics:

- A Source with **one** junction row funds one project.
- A Source with **N** junction rows is shared across those N projects. Each project has its own amount and window.
- Sizing is per-project: Project 1 may auto-size its share; Project 2 may fix its share.
- The Source's scenario-wide effective window = union of per-project windows (`min(active_from)`, `max(active_to)`). Drives reporting only; the engine uses per-project windows.

### 3. Waterfall becomes per-project

Add `project_id UUID NOT NULL FK projects.id` to `waterfall_tiers` and `waterfall_results`. Keep `scenario_id` for scoping queries (derivable, but explicit helps).

- Each Project has its own ordered tiers, its own LP/GP splits, its own hurdles.
- Waterfall computation runs per project against that project's levered cash flow.
- The "joined" Underwriting waterfall is a reporting concatenation — all projects' tiers displayed together. Combined Underwriting IRR is computed on the **summed levered cash flow**, not via a recomputed waterfall.

**Migration backfill:** for existing scenarios, all tiers get the default project's id. One project per scenario today → no semantic change.

### 4. UseLine gets `source_capital_module_id` (nullable)

- NULL for user-entered uses (unchanged).
- Populated for engine-injected reserves (IR, CI, Acq Interest, Lease-Up Reserve).
- Each project has its own reserve UseLines on its own Sources. Summing reserves across projects gives the deal-level reserve total — the user's requested "calculate uses separately for each project, summing them for deal reserves."

### 5. DrawSource is per-project

`DrawSource.project_id UUID NOT NULL FK projects.id`. A shared Source has one `DrawSource` row per project it funds. Each row tracks that project's own draws on that Source.

### 6. Cross-project milestone triggers (relational timelines)

Today `milestones.trigger_milestone_id` references another milestone on the same project. Extend: allow it to reference a milestone on **any project in the same scenario**. FK stays `milestones → milestones` — only the validation/resolver changes.

Also add, for clarity and easy UI editing at the Underwriting layer, a new table: **`project_anchors`**.

Semantics:

- `anchor_project_id IS NULL` → project starts on its own `start_date` (today's behavior).
- `anchor_project_id` set → project's first milestone computes as `anchor_project`'s `anchor_milestone`'s end_date + offset. From there, the project's internal trigger chain (`trigger_milestone_id`) resolves normally.
- **Circular anchors rejected at write time** (DFS cycle check, scoped to scenario).

The `project_anchors` table is the user-facing Underwriting timeline configuration. The `milestones.trigger_milestone_id` extension handles the lower-level chain walk that `computed_start()` already performs.

---

## Proposed Math

### Calc invocation shape (single entry point per Scenario)

**Key corollary of shared draws:** once any Source is shared between ≥2 projects, those projects' carry numbers are **coupled** — P2's pro-rata share of the shared balance depends on P1's uses, and vice versa. Computing P2 alone with stale P1 draws silently produces wrong carry that cascades into wrong cashflow, wrong waterfall, wrong IRR.

**Therefore: the unit of calculation is the Scenario (= Underwriting), not the Project.** A single "Calculate" button per Scenario runs the full pipeline. Per-project calc is an optimization available only when a project has zero shared Sources (all its Sources are attached only to itself) **and** no downstream anchor dependents exist. In practice, as soon as the deal has any shared Source, Calculate always runs the whole thing.

The pipeline is ordered so most of the expensive work still runs per-project in isolation:

#### Phase 0 — Date resolution (cross-project, cheap)

Topo sort over `project_anchors`. Resolve each project's start date + its full milestone timeline.

#### Phase 1 — Per-project standalone pass (parallelizable)

For each project, in topo order, compute using only that project's inputs + resolved dates:

- Use lines (user-entered), income, opex.
- Standalone Sources (Sources attached to this project only): size, draw schedule, carry, reserve UseLines.
- Standalone cashflow + waterfall.
- Shared-Source lines in this project are **placeholders** for now — sized to the project's own uses under that Source (best guess), carry marked `pending_shared_resolution`.

#### Phase 2 — Shared-Source joint resolution

For each shared Source (junction rows > 1), across all covering projects at once:

- **Joint sizing:** apply the existing self-referential formula with `uses = Σ covering_projects' uses in window`, single draw cadence.
- **Joint draw schedule:** one schedule per Source. Each draw event's amount reflects combined uses in window.
- **Per-project balance attribution:** each project's share of outstanding balance = running Σ of `(its uses in each window / total uses in that window) × draw amount`.
- **Per-project carry writeback:**
  - `io_only` / `pi`: each project's monthly `debt_service` share = `total_DS × (project_balance_share / total_balance)`.
  - `interest_reserve` / `capitalized_interest`: each project's reserve UseLine re-sized to its own uses-under-this-Source × carry factor (uses that project's own `_loan_pre_op_months` on the shared Source).
- Overwrite Phase 1 placeholders.

#### Phase 3 — Per-project cashflow + waterfall recomputation (affected projects only)

For each project whose carry changed in Phase 2, re-run its period loop with corrected carry and re-run its waterfall.

#### Phase 4 — Underwriting rollup (unchanged from earlier section)

Timeline, draws, cashflow, Source package, joined waterfall, combined IRR.

> Phases 2–3 are skipped entirely when no Sources are shared. For single-project Scenarios, Phase 0 collapses, Phase 2–3 are noops, and the pipeline equals today's engine call.

### Reconciliation rules: hard at Project, soft at Deal

The status pill today flags DSCR, LTV, and Sources-vs-Uses gap, and some of those checks feed back into auto-sizing (DSCR-capped permanent debt). In a multi-project Underwriting this must split:

#### Project-level rulesets — HARD (drive sizing)

- Sources = Uses per project (fundamentally enforced by per-project sizing).
- `dscr_minimum` cap on perm debt sizing.
- `ltv_pct` cap by `funder_type`.
- `construction_floor_pct`.
- Debt sizing mode (`gap_fill` / `dscr_capped` / `dual_constraint`).
- Reserve floors.

These are inputs the engine uses to solve for Source amounts at the Project level. Unchanged from today.

#### Deal / Underwriting rulesets — SOFT (notify only)

- Combined DSCR across all projects on a shared Source (lender-level portfolio DSCR).
- Combined LTV across the shared loan's collateral pool.
- Any aggregate the user wants to monitor but that has no mechanical fix at the engine level.

Sources-vs-Uses at the Underwriting level falls out of project balances automatically; displayed as derived status, never independently enforced.

**The engine cannot automatically "downsize a loan in a randomly selected project" to satisfy a Deal-level rule. That's a human decision.** So Deal-level violations show as pill warnings with a drill-down to which projects contribute, and the user decides where to intervene. No auto-sizing cascades from Deal rules back into Project sizing in v1.

#### Pill surface area

- Each project has its own pill: `Computed` / `Stale` / `DSCR` / `LTV` / `Sources gap` / `Failed`.
- The Underwriting has its own pill: `Computed` / `Stale` / `Combined-DSCR alert` / `Combined-LTV alert` / `Failed`.
- A single view ("Status") lists all per-project + Underwriting pills.

**Data model addition (small):** status rows written by the engine during calc, read by the UI for pills. Cleared/rewritten on each calc. No legacy columns to migrate — the pill today reads scenario state directly, we just make it read from this table going forward.

### Staleness & automatic recompute

Each project output row stores `computed_at`. Each input table stores `updated_at`. An output is stale when any upstream input's `updated_at > computed_at`. The Underwriting rollup is stale when any project output is stale.

"Calculate" recomputes everything stale, in topo order, automatically. The UI surfaces staleness per project and at the Underwriting level. **Users never need to reason about "should I calc P1 first" — the button does the right thing.**

### A. Resolve cross-project dates first (Underwriting pre-pass)

Before any project computes:

1. Build a DAG from `project_anchors` (node = project, edge = `anchor_project_id → project_id`).
2. Reject cycles.
3. Topological sort → compute order.
4. For each project in that order: resolve its effective `start_date` by walking the anchor to the upstream project's already-resolved anchor milestone and applying `offset_months + offset_days`. The project's own milestone chain (intra-project `trigger_milestone_id`s) still resolves normally from there.
5. Cache resolved project start dates + all resolved milestone dates for the per-project engine to consume.

This makes the coupling explicit: P2's cashflow depends on P1's cashflow **only through date resolution**. Money doesn't flow between them; only timing does.

### B. Per-project engine runs unchanged (mostly)

For each project in `topo_order(scenario.projects)`:

1. Resolve this project's Sources via the junction — each junction row becomes a logical per-project `CapitalModule` view carrying the shared identity (rate, carry_type, lender) plus the per-project terms (amount, window, sizing flag).
2. Run the existing engine against this project's uses, income, opex, milestones, and its view of Sources.
3. Persist per-project `CashFlow`, `WaterfallResult`, `OperationalOutputs`, per-project reserve UseLines (tagged with `source_capital_module_id`).

No changes to `_auto_size_debt_modules`, `_loan_pre_op_months`, `_compute_period`, `compute_waterfall`. The engine sees a single-project world per invocation, exactly like today.

### C. Underwriting rollup (new layer)

After all projects compute, produce the Underwriting. **Pure aggregation — no new sizing, no new carry math.**

- **Timeline** — union of per-project milestone windows per phase. For a shared Source, effective window is `min(starts) → max(ends)` across projects that include it.
- **Draw schedule** — per month T, total draw on Source A = Σ over projects p that include A of `draw(A, p, T)` from the per-project `DrawSource` output.
- **Cash flow** — per month T, Underwriting cashflow = Σ over projects of project's cashflow row at T. Each component (revenue, opex, NOI, debt_service, capex, net_cf) sums naturally.
- **Source package** — one row per `CapitalModule` (shared Sources deduped by identity):
  - `principal` = Σ `junction.amount` across projects
  - `drawn_to_date` = Σ per-project draws
  - `outstanding_balance(T)` = Σ per-project balances
  - Rate, carry_type, lender unchanged (they live on the `CapitalModule` itself)
- **Reserves** — each project's reserve UseLines already carry `source_capital_module_id`. Underwriting reserve total per Source = Σ of project-level reserves on that Source. Satisfies "calculate separately per project, sum for deal reserves."
- **Waterfall** — joined table displays all per-project tiers side-by-side (project column + tier rows). No cross-project waterfall math.
- **IRR** — combined Underwriting IRR = XIRR on the summed levered cash flow across all projects. Each project also retains its standalone IRR.

### D. Sources = Uses invariant

Now holds at both levels naturally:

- **Per project:** `Σ(sources on project) ≈ Σ(uses on project) + per-project IO carry + per-project reserves`. Same invariant as today.
- **Underwriting:** `Σ(per-project invariant) → Σ(total sources) ≈ Σ(total uses) + Σ(total IO) + Σ(total reserves)`. Falls out by additivity. Nothing new to enforce.

### E'. Shared Source draw cadence (Scenario A, with per-project carry attribution)

A shared Source has **one draw schedule**, not one per project. This matches real lender mechanics (monthly batch requisitions on one loan) and leverages the existing windowing in [draw_schedule.py](../app/engines/draw_schedule.py).

**Mechanics:**

- Source's `draw_every_n_months` lives on the `CapitalModule` (shared across projects).
- Per draw event at month T: window = `[T, next_draw_T)`. Draw size = Σ uses in window across all covering projects + per-loan carry fold-in (existing self-referential formula, unchanged).
- The drawn balance is attributed **pro-rata** to each covering project by that project's share of uses in the window.
- Running `project_balance_share[p]` = cumulative Σ of per-draw shares minus any project-level payoffs.
- Monthly carry for this Source per project:
  - `io_only` / `pi` → project's `debt_service` share = `total_DS × (project_balance_share[p] / total_balance)`.
  - `interest_reserve` / `capitalized_interest` → each project's IR / CI UseLine (already injected per-project, already tagged with `source_capital_module_id`) accrues against that project's uses under this Source.

This means the "early carry" case (P2's use falls 15 days after a draw) shows up honestly: **P2 pays carry on its own share from draw date, not from use date**. No carry is magically moved to P1.

The Underwriting view still shows one combined draw schedule row per Source per month (summed across projects). Drill-down shows the per-project share.

> **Non-goal for v1:** "per-project draw cadence on a shared Source" (Scenario B). If ever needed later, it's an opt-in Source flag without schema change — the junction already has the fields for per-project windows.

### E. Shared Source sizing mechanics

When Source A is shared between Projects 1 and 2:

- If both projects' junction rows have `auto_size=TRUE`: each project independently sizes its share against its own uses under Source A. Combined principal = sum.
- If one fixes and one auto-sizes: each honors its own mode against its own uses. No negotiation.
- If both fix: shares are user-specified; Source A's scenario-wide principal = sum of fixed amounts.

Nothing in the engine needs to know whether a Source is "shared" — that's purely a junction concept surfaced at the Underwriting layer.

### F. Project is the only computation unit (for money)

The engine never looks across projects for money. It only reads pre-resolved cross-project dates. This lets us keep `_auto_size_debt_modules`, `_compute_period`, and `compute_waterfall` essentially untouched. A small wrapper hydrates the junction row + resolved dates into a `CapitalModule`-shaped object. **No behavioral change inside the hot path.**

---

## Variant Duplication Semantics

When a user creates a Variant from an existing Scenario (`create_deal_copy` at [app/api/routers/ui.py:5195](../app/api/routers/ui.py#L5195)), the copy must carry **inputs only** — never the computed Underwriting.

### Copy (inputs — define the deal)

- `Project` rows + their `UseLine`s (user-entered only), `IncomeStream`s, `OperatingExpenseLine`s, `OperationalInputs`, `UnitMix`, `Milestone`s
- `CapitalModule` rows (Source identities) + `capital_module_projects` junction rows (per-project terms)
- `project_anchors` (relational timeline config)
- `WaterfallTier` rows (per-project tier definitions)

### Do NOT copy (outputs — must recompute)

- `CashFlow` / `CashFlowLineItem` rows
- `WaterfallResult` rows
- `OperationalOutputs`
- Engine-injected reserve `UseLine`s (rows where `source_capital_module_id IS NOT NULL`)
- `DrawSource` rows (these are engine-written draw projections, not user config)
- Any new `underwriting_*` rollup tables

On variant creation the Variant starts with an **empty Underwriting**. User edits inputs, clicks Compute → per-project engine runs, Underwriting rollup runs, outputs persist for this Variant only.

This boundary (input vs output) is the cleanest way to guarantee variants don't carry stale numbers. To keep the rule mechanical, mark every output table with a comment header `# UNDERWRITING OUTPUT — do not copy on variant creation` and have `create_deal_copy` consume an **explicit allow-list** of tables to copy (fail-closed if a new table isn't classified).

---

## Migration Strategy

### `0042_multi_project_underwriting`

1. Create `capital_module_projects` junction.
2. **Backfill:** for each existing `CapitalModule`, insert one junction row for `(module, default_project)` with `amount = source.amount`, `auto_size = source.auto_size`, windows = current `active_phase_start/end` on module.
3. Add `waterfall_tiers.project_id`, `waterfall_results.project_id`; backfill to default project.
4. Add `use_lines.source_capital_module_id` (NULL; no backfill required — next compute populates reserves correctly).
5. Add `draw_sources.project_id`; backfill to default project.
6. Keep legacy columns on `CapitalModule` (`active_phase_start/end`, `source.amount`) for one release as derived / display values synced from junction. Remove in a later migration.

### Engine cutover

- Add helper `_source_view_for_project(module, project_id) → CapitalModuleView` that hydrates per-project terms from junction.
- Change engine entry from "pick default project" to "loop over all projects," each invocation building its own Source views from the junction.
- For scenarios with one project and empty coverage overrides → byte-identical output to today.

### Underwriting rollup

New module `app/engines/underwriting.py` (or `app/engines/rollup.py`) with pure aggregation functions (`rollup_cashflow`, `rollup_draws`, `rollup_sources`, `rollup_waterfall`, `rollup_irr`).

- Called after per-project computation completes.
- Output persisted to new `underwriting_results` table (or derived on read — decide based on compute cost; single-project scenarios should short-circuit to project output).
- **Reuse existing utilities:**
  - `pyxirr.xirr` for combined IRR — same import as per-project IRR.
  - `Decimal` arithmetic throughout — enforce via `MONEY_PLACES` constant in [cashflow.py](../app/engines/cashflow.py).
  - Gantt builder already aggregates across projects (`_build_gantt_rows` at [app/api/routers/ui.py:675](../app/api/routers/ui.py#L675)) — reuse for timeline rollup.

---

## Critical Files

| Area | File | Change |
|---|---|---|
| Migration | `alembic/versions/0042_multi_project_underwriting.py` | **New** — junction, `waterfall.project_id`, `use_lines.source_capital_module_id`, `draw_sources.project_id`, `project_anchors`, backfills |
| Model | [app/models/project.py](../app/models/project.py) | `ProjectAnchor` ORM model; `Project.anchor` relationship |
| Model | [app/models/milestone.py:85](../app/models/milestone.py#L85) | Relax `trigger_milestone_id` validator to allow same-scenario cross-project references; add scenario-scoped cycle check |
| Engine | `app/engines/underwriting.py` | **NEW** — pre-pass: topo sort, resolve project start dates; post-pass: rollup |
| Model | [app/models/capital.py:43](../app/models/capital.py#L43) | `CapitalModule` keeps identity; add `project_terms` relationship to junction |
| Model | `app/models/capital.py` (new class) | `CapitalModuleProject` junction ORM model |
| Model | [app/models/capital.py:79](../app/models/capital.py#L79), [:114](../app/models/capital.py#L114) | Add `project_id` to `WaterfallTier`, `WaterfallResult` |
| Model | [app/models/capital.py:146](../app/models/capital.py#L146) | Add `project_id` to `DrawSource` |
| Model | [app/models/deal.py:460](../app/models/deal.py#L460) | Add `source_capital_module_id` to `UseLine` |
| Schema | [app/schemas/capital.py](../app/schemas/capital.py) | `CapitalModuleProjectSchema`, per-project terms |
| Engine | [app/engines/cashflow.py:47](../app/engines/cashflow.py#L47) | `compute_cash_flows` loops per project; builds per-project Source view |
| Engine | [app/engines/cashflow.py:1001](../app/engines/cashflow.py#L1001) | `_auto_size_debt_modules` consumes per-project Source view (no algorithmic change) |
| Engine | [app/engines/cashflow.py:1574](../app/engines/cashflow.py#L1574), [:1760](../app/engines/cashflow.py#L1760) | Reserve `UseLine`s get `source_capital_module_id` set |
| Engine | [app/engines/draw_schedule.py:186](../app/engines/draw_schedule.py#L186) | `DrawSource` rows written per-project |
| Engine | [app/engines/waterfall.py:79](../app/engines/waterfall.py#L79) | `compute_waterfall(project_id=…)` — per-project scope |
| Engine | `app/engines/underwriting.py` | **NEW** — rollup: timeline, draws, cashflow, sources, reserves, joined waterfall, combined IRR |
| Regression | [scripts/test_phase_b_debt.py](../scripts/test_phase_b_debt.py) | Add: (a) single-project unchanged, (b) 2 projects no sharing, (c) 2 projects one shared Source, (d) 3 projects mixed coverage |
| Variant copy | [app/api/routers/ui.py:5195](../app/api/routers/ui.py#L5195) (`create_deal_copy`) | Switch to explicit copy allow-list (inputs only); strip all Underwriting outputs + junction-written draws |

---

## Verification

**Byte-identical backward compat:** pick 5 existing single-project scenarios from prod; diff per-project output before/after migration + engine cutover. Must equal to the `Decimal`.

### Unit tests (`tests/engines/`)

- **`test_shared_source_sizing`** — one Source on 2 projects, `auto_size` each, principal = sum.
- **`test_shared_source_windows`** — per-project windows resolve independently; Underwriting timeline = union.
- **`test_reserve_split_by_project`** — IR on shared construction loan: each project has its own IR `UseLine` with `source_capital_module_id` set; sum = deal reserve.
- **`test_combined_irr`** — Underwriting IRR = `XIRR(sum of per-project levered CF)`; matches hand calc.
- **`test_joined_waterfall_table`** — 2 projects each with 3 tiers → joined table has 6 rows with `project_id`.
- **`test_anchor_propagation`** — P2 anchored to `P1.acquisition_close+6mo`. Shift `P1.start` by 3mo → P2's entire cashflow shifts by 3mo; shapes unchanged.
- **`test_anchor_cycle_rejected`** — P1 anchored to P2 and P2 anchored to P1 → write-time error.
- **`test_anchor_topo_order`** — P3 anchored to P2, P2 anchored to P1 → compute order is P1→P2→P3.
- **`test_variant_copy_excludes_outputs`** — duplicate a Scenario with computed Underwriting; variant has zero `CashFlow` / `WaterfallResult` / engine-written reserve `UseLine`s / `DrawSource` rows. Inputs (Projects, Sources, junction, anchors, WaterfallTiers) all present.
- **`test_variant_recompute_independence`** — mutate a Source amount on the variant; parent Scenario's Underwriting unchanged.
- **`test_shared_source_joint_sizing_phase2`** — P1 has $10M uses, P2 has $5M uses, both `auto_size` on shared Source A. After calc, Source A principal = ~$15M + joint IO carry; P1 balance share → uses ratio; each project's DS share sums to total DS.
- **`test_coupling_recompute_on_p1_edit`** — after full calc, edit P1 uses. Mark P1 + P2 stale (both covered by shared Source). Recompute → P2 carry changes even though no P2 input moved.
- **`test_standalone_projects_skip_phase2`** — Scenario with no shared Sources; assert Phase 2/3 are noops; per-project cashflow byte-identical to single-project engine today.
- **`test_hard_rule_drives_sizing`** — DSCR min violated on P2's perm loan → engine downsizes P2's perm (existing behavior); no cross-project cascade.
- **`test_soft_rule_underwriting_only`** — combined-DSCR threshold violated at Underwriting level → `rule_violations` row with `scope='underwriting'`, `severity='soft'`, no engine-driven Source resizing anywhere.

### Phase B regression

[scripts/test_phase_b_debt.py](../scripts/test_phase_b_debt.py) — new fixtures for shared / disjoint / mixed sharing.

### Live smoke

Seed a multi-project deal on prod, walk through per-project compute then Underwriting rollup; verify Sources = Uses at both levels and combined IRR matches per-project weighted sum.

---

## Non-Goals (explicit for v1)

- **No cross-project waterfall recomputation** (joined-table only).
- **No scenario-level milestones** — timing is per-project on the junction; cross-project coupling is via `project_anchors`.
- **No per-project divergence of `OperationalInputs` enforcement** — each project already has its own.
- **UI is out of scope**; assume upcoming UI overhaul consumes the new data model.
  - *Flagged for the UI overhaul:* the rule-violation surface grows substantially — per-project pills × N projects + a separate Underwriting pill + drill-down from each Underwriting soft alert to contributing projects. The `rule_violations` table is designed to make this display straightforward (filter by `scope` / `project_id` / `severity`).
- **No cross-project cash sweeps or cross-collateralization payouts in v1.** Coupling is date-only. If a future version wants shared reserve sweeps, it belongs in a later phase.
