# UI Needs — Known Challenges and Refactor Requirements

**Status**: Tracking document — updated as issues are identified
**Last updated**: 2026-04-16
**Context**: The engine and data model are being refined first. This document captures UI work to inform a future refactor once the model stabilizes.

---

## Philosophy

An accurate model that is hard to use is a good problem to have. A pretty app that lost function over form is a bad problem to have. The UI refactor happens AFTER the data model is stable.

---

## Architectural Issues

### 1. Input/Output Flip-Flop
**Problem**: Users constantly switch between Deal Setup Wizard (inputs) and Model Builder tabs (outputs). No way to see both simultaneously.
**Solution**: Side-by-side layout — collapsible sidebar showing relevant inputs alongside the output view. Pro Forma tab shows rent/vacancy/escalation sidebar. Cash Flow tab shows debt terms sidebar.
**See**: [model-builder-architecture.md](feature-plans/model-builder-architecture.md)

### 2. Input Authority Confusion
**Problem**: Some fields are editable in multiple places (e.g., unit count appears in UnitMix AND Income Streams). No enforcement of where edits should happen.
**Solution**: Input authority map — each field has ONE canonical edit location. Other views are read-only displays. Example: unit count editable in Building Editor only, displayed (not editable) in Revenue tab.

### 3. No Model Consistency Validation
**Problem**: When upstream inputs change (unit count, exit cap, debt terms), downstream values may become stale. No notification. User discovers inconsistencies accidentally.
**Solution**: Persistent notification center with model validation rules. Issues visible from any tab. Clearable only by resolving, not dismissing. Logged with timestamps for audit trail.

### 4. Building Editor Not Always Visible
**Problem**: UnitMix editor is hidden for single-parcel/single-building deals. Need to always show the building editor — it's where market rent, in-place rent, and unit strategy assignments live.
**Solution**: Always render building editor regardless of parcel/building count.

---

## Visual / Styling Issues

### 5. CSS Inconsistencies
**Problem**: Styles vary across pages — different spacing, font sizes, border treatments. No design system.
**Solution**: Define a component library (stat cards, form fields, tables, panels, buttons) with consistent tokens. Apply globally.

### 6. Color Scheme
**Problem**: No deliberate color palette. Mix of hardcoded colors and CSS variables. Investor-facing exports use a separate palette from the app.
**Solution**: Define primary/secondary/accent/surface palette. Dark mode consideration. Professional CRE aesthetic (deep navy, clean whites, muted accents — similar to investor export palette).

### 7. Labeling Inconsistencies
**Problem**: Terminology varies. "Deal Model" vs "Scenario" vs "Model". "Revenue" vs "Income". "Sources" vs "Capital Stack". Phase names don't always match between wizard and builder.
**Solution**: Terminology audit. Define canonical names in CLAUDE.md and enforce across all templates.

### 8. Project Type Language
**Problem**: "Minor Renovation" actually means "Deferred Maintenance" (not adding value, just catching up to market). "Major Renovation" means "Value-Add." These labels mislead users.
**Solution**: Rename project types to match business intent:
- `acquisition` → `acquisition_deferred_maintenance` or `acquisition_ltl_catchup`
- `value_add` → `acquisition_value_add`
- Keep internal enum values for backward compat, change display labels.

---

## Missing UI Components

### 9. New Fields Without UI (from April 16 engine work)

| Field | Model | Has Backend | Has UI | Priority |
|---|---|---|---|---|
| `asset_mgmt_fee_pct` | OperationalInputs | Yes | No — needs location decision (user/org setting vs deal-level) | Medium |
| `lease_up_curve` | OperationalInputs | Yes | Partial — needs wizard integration | High |
| `lease_up_curve_steepness` | OperationalInputs | Yes | Partial — needs wizard integration | High |
| `market_rent_per_unit` | UnitMix | Yes | No — needs building editor integration | High |
| `in_place_rent_per_unit` | UnitMix | Yes | No — needs building editor integration | High |
| `renovation_absorption_rate` | IncomeStream | Yes | No — needs income stream form addition | Medium |
| `renovation_capture_schedule` | IncomeStream | Yes | No — decided not to expose in UI (continuous ramp only) | N/A |
| `refi_cap_rate_pct` | CapitalSourceSchema | Yes | No — show only when dual_constraint sizing | Low |
| `sensitivity_matrix` | OperationalOutputs | Yes (storage) | No — needs dedicated tab with compute trigger | High |

### 10. UnitMix Strategy Assignment UI
**Problem**: No way to assign per-unit-type strategies (base escalation, LTL catchup, value-add renovation).
**Solution**: Strategy dropdown per row in UnitMix editor. "Apply to Model" button auto-generates income streams.
**See**: [model-builder-architecture.md](feature-plans/model-builder-architecture.md)

### 11. Sensitivity Analysis Tab
**Problem**: No sensitivity analysis visualization.
**Solution**: New tab below Cash Flow. Two-axis dropdown (default: exit cap × rent growth). Target metric dropdown (default: Levered IRR). 5×5 color-coded grid. "Run Sensitivity" button triggers 25 compute cycles. Read-only — does NOT feed back into model.

### 12. Refi/Prepay Line Items in Cash Flow View
**Problem**: Refi net proceeds and prepay penalty line items are generated by the engine but not explicitly called out in the cash flow table display.
**Solution**: These already appear as CashFlowLineItem rows. The CF table template may need to style them distinctly (e.g., indented, different color) so the refi event is visible.

---

## Deal Setup Wizard Improvements

### 13. Step 4 (Debt Terms) Growing Complex
**Problem**: Three sizing modes (gap-fill, DSCR-capped, dual-constraint), LTV input, DSCR minimum, per-loan terms. Getting crowded.
**Solution**: Consider splitting debt into sub-steps or a tabbed layout within step 4.

### 14. No Wizard Step for Waterfall / Partnership Terms
**Problem**: Waterfall tiers are configured in the model builder, not the wizard. AM fee has no home.
**Solution**: Add a wizard step for partnership structure: waterfall tiers, AM fee, sponsor/LP splits.

### 15. Default Expense Categories
**Problem**: Deal setup doesn't seed a standard set of expense lines matching industry consensus.
**Solution**: Auto-seed from consensus list: RE Taxes, Insurance, Utilities, R&M, Management Fee, Payroll, Marketing, G&A, Turnover/Make-Ready, CapEx Reserve. User deletes what doesn't apply.

---

## Data Display Issues

### 16. Cash Flow Table — Monthly vs Annual Toggle
**Problem**: Cash flow shows monthly detail. Investors want annual summaries. No toggle.
**Solution**: Add monthly/annual toggle. Annual view sums 12-month buckets. This is also needed for the investor Excel export.

### 17. Sources & Uses — No Reconciliation Display
**Problem**: No visible "Sources - Uses = Gap/Surplus" line. User has to mentally check balance.
**Solution**: Add reconciliation row at bottom of S&U panel with color indicator (green = balanced, red = gap).

### 18. Waterfall Distribution Timeline
**Problem**: No visualization of LP/GP cash flows over time.
**Solution**: Per-period distribution chart or table showing LP vs GP cash flows, cumulative distributions, and return metrics per period.

---

## Performance / Technical

### 19. ui.py at 8,000+ Lines
**Problem**: Single monolithic route file. Hard to navigate, slow linting.
**Solution**: Split into sub-routers (auth, listings, deals, model_builder, parcels, etc.).

### 20. Template Includes vs Components
**Problem**: Templates use `{% include %}` for partials but no component abstraction. Repeated patterns (stat cards, form fields) are copy-pasted.
**Solution**: Jinja2 macros for common components. Or evaluate a lightweight component approach.

---

## Multi-Project Underwriting — Engine ready, UI not (as of 0051)

*Engine / schema status as of 2026-04-21.* Phase 1 (migration 0048) and Phase 2 (migrations 0050 / 0051 + engine refactor) landed and verified byte-identical on prod. The cashflow engine now loops per project, writes per-project output rows, and exposes a scenario-level rollup via `app/engines/underwriting_rollup.py`. What's missing is the UI that lets a user see / edit / compute multi-project deals.

### Deferred engine work (documented invisible capabilities)

These have schema and partial code in place but no UI to exercise. Each line below names a *trigger* — the UI capability that has to land before the matching engine work is worth finishing.

| # | Engine item | Needed when the UI… |
|---|---|---|
| A | **Junction overlay (2c1)** — route auto-sizing to read/write `capital_module_projects.amount` instead of `CapitalModule.source.amount`. Read-side helpers (`is_shared_source`, `junction_amount_for`) exist; overlay needs a deeper refactor of `_auto_size_debt_modules` because its writeback path targets the module's source dict. | …lets the user set divergent per-project amounts on a shared Source via the coverage modal. |
| B | **Anchor-driven dates (2d1)** — walk `project_anchors` chain, compute per-project start-date offsets, seed milestone-date overrides into each project. `anchor_resolver.ordered_projects` detects cycles and orders compute; date math is not yet computed. | …offers a "Project B starts 6 months after Project A's close" UX. Current product direction is *not needed* — each project has its own start date via the wizard, and the Deal / Underwriting start = min(project starts). |
| C | **Reserve attribution for aggregates (2e1)** — Operating Reserve and Lease-Up Reserve are engine-aggregated across multiple modules; tagging them with a single `source_capital_module_id` requires a split or representative-module decision. Bridge IO and closing-cost reserves are already tagged (Phase 2e). | …shows per-Source reserve totals in the Underwriting Source Package panel. |
| D | **Joint draw cadence (2f)** — emit one DrawSource row per shared Source, per-project balance-share attribution, per-project carry on draw date. At month-level resolution (current engine) this produces identical numbers to independent per-project — meaningful only once the engine has day-level modeling. Deferred indefinitely. | …a real shared-lender deal is configured AND day-level timing becomes a product requirement. |

### UI work — top of Phase 3

### 21. Underwriting rollup tab

Migration `0048_multi_project_underwriting` landed the data foundation for one Scenario carrying N Projects with shared-Source capital packages and cross-project timelines. The engine and UI still operate in single-project mode. These items are the UI work that needs to land before users can exercise the new schema. See `docs/Underwriting Plan.md` (data-model plan) and `~/.claude/plans/start-planning-out-the-synthetic-squirrel.md` (approved UI plan) for the full design.

### 21. Underwriting rollup tab
**Status**: schema in, no UI.
**Problem**: a Scenario with N Projects has no combined view — no joined timeline, no combined cashflow, no deduped Source package, no combined IRR, no joined waterfall table. The Model Builder shows one Project at a time.
**Solution**: new `[Underwriting] [Project 1] [Project 2] …` tab row under the Variant tabs. Underwriting tab renders `underwriting_pill`, `underwriting_source_package`, `underwriting_timeline`, `underwriting_cashflow`, `underwriting_waterfall`, `underwriting_kpi_strip` partials. Short-circuits to per-project output when there's only one Project.

### 22. Source ↔ Project coverage (junction editor)
**Status**: `capital_module_projects` table populated (1:1 backfill), no UI.
**Problem**: a CapitalModule today shows a single scenario-level amount / active window. Shared Sources need per-project amounts, windows, and `auto_size` flags.
**Solution**: "Coverage" button on each Source row opens a modal with per-project rows (include toggle, amount, active_from/to, auto_size). POSTs to `/ui/models/{id}/sources/{source_id}/coverage`.

### 23. Project anchors (relational timelines)
**Status**: `project_anchors` table exists, zero rows, no UI.
**Problem**: can't express "Project 2 starts 6 months after Project 1's acquisition close." Users wanting coupled timelines have no way to declare the link.
**Solution**: anchors panel under the Underwriting timeline. Inline PATCH to `/ui/models/{id}/anchors/{project_id}`. Server-side DFS cycle check rejects P1→P2→P1.

### 24. Per-project status pills + Underwriting pill
**Status**: today's pill is scenario-level monolithic HTML at `_render_calc_status_pill_html`.
**Problem**: with N Projects, DSCR/LTV/Sources=Uses must be checked per project, plus lender-level combined rules (combined DSCR, combined LTV) at the Underwriting level.
**Solution**: promote pill HTML into a parameterized partial (`partials/calc_status_pill.html`). Split `_compute_calc_status` into `_compute_project_status(data, project_id)` + `_compute_underwriting_status(data)`. Render one pill per tab chip.

### 25. Staleness dots (explicit recompute signal)
**Status**: no output freshness tracking today; pill silently displays last-computed numbers.
**Problem**: shared Sources couple projects — editing Project 1 invalidates Project 2's carry math. Users have no way to see that an output is stale.
**Solution**: `computed_at` on outputs, `updated_at` on inputs. Amber dot on tab chips when `max(input.updated_at) > min(output.computed_at)`. Calculate button on Underwriting tab runs the full pipeline.

### 26. Reserve → Source attribution in Uses panel
**Status**: `use_lines.source_capital_module_id` column exists, nullable, unpopulated.
**Problem**: engine-injected reserves (IR / CI / Acq Interest / Lease-Up Reserve) only show `(auto)` today with no hint which Source they originated from.
**Solution**: engine sets `source_capital_module_id` on reserve writes (Phase 2). UI Uses panel shows a `from: {source.label}` chip next to `(auto)`.

### 27. Per-project waterfall + joined display
**Status**: `waterfall_tiers.project_id` backfilled, but tier editor still scenario-scoped.
**Problem**: waterfall UI assumes one set of tiers per Scenario.
**Solution**: tier editor scoped to active Project; Underwriting tab shows joined table with a `Project` column.

### 28. Variant copy allow-list update
**Status**: `create_deal_copy` at `ui.py:5295` copies Projects + UseLines + Sources + Tiers but doesn't yet copy junction rows or anchors.
**Solution**: extend allow-list to include `CapitalModuleProject` and `ProjectAnchor`. Post-copy, land on Underwriting tab with all projects' staleness dots lit.

---

## Recently fixed

- **[2026-04-21, 0051]** Phase 2 engine refactor shipped: cashflow engine now loops per project, writes per-project output rows, exposes scenario-level rollup via `app/engines/underwriting_rollup.py`. Byte-identical verified against 5 prod baseline scenarios (`tests/phase2_baseline/*.json`). Migrations 0050 / 0051 added `project_id` to output tables and swapped UNIQUE constraint on operational_outputs.
- **[2026-04-20, 0049]** Sidebar module-card hrefs now preserve `?project=<id>` so navigating between modules no longer silently bounces the user back to the default Project. Previously users on Project 2 who clicked "Timeline" in the sidebar lost their project context because the href used `{{ request.url.path }}?module=xxx` without the project param.
- **[2026-04-20, 0049]** Stale `ProjectType` enum values (`acquisition_minor_reno` etc.) from the 2026-04-19 rename are now backfilled. Compute no longer crashes with `ValueError: Unsupported project_type` on pre-rename deals.

---

*This document is a living tracker. Add items as they're identified. Remove items when resolved. Don't wait for the UI refactor to fix critical usability blockers.*
