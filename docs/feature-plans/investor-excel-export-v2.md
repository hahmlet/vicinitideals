# Investor-Ready Excel Export — Build Plan

**Status:** Approved for build (2026-04-25). Supersedes the rough plan in
`investor-excel-export.md` (which was the v1 scoping note).

**Audience:** another agent or contributor will execute this from scratch.
This doc is everything they need to start.

**Build sequencing relative to the schema refactor.** This export is being
built **before** the opportunities/buildings/parcels refactor in
[`opportunities-buildings-refactor.md`](./opportunities-buildings-refactor.md).
The pure-math layer (cashflow, waterfall, IRR, DSCR, draw schedule) is
unaffected by the refactor, so commits 0–3 ship now. The narrow set of
data-load and assumptions-sheet touchpoints that the refactor will move
(`unit_mix` shape, `acquisition_price` source, `deal_type` → `proposed_use`,
opportunity lineage) are addressed in **commit 4** below. Commit 4 is
not optional — it's the post-refactor patch that keeps this export
compatible once the schema rewrite lands.

---

## 1. Goal & Non-Goals

**Goal:** generate a single `.xlsx` workbook per Scenario that an LP / lender
would expect to receive — investor-summary first, per-project detail second,
audit material last. Hard-coded values for now; named ranges everywhere so
Phase 2 can swap values for formulas without restructuring the file.

**Non-goals:**

- The existing round-trip exporter at
  [`app/exporters/excel_export.py`](../../app/exporters/excel_export.py) is
  **deprecated** as of this build (see §10). Don't extend it; keep it
  compiling and the existing tests green so we have a safety net during
  rollout, but it's on track for removal once the investor export is the
  canonical artifact. A future "simplified underwriting" extract may live
  alongside the investor export, but that comes *after* the math doc is
  trustworthy and the investor export is complete.
- No formulas in this phase. `CellRegistry` (below) makes Phase 2 a swap, not
  a rewrite.
- No PDF, no charting, no print-area tweaks beyond freezing panes.
- No multi-scenario rollup. One workbook per Scenario.

---

## 2. Sheet Order (final)

```
1.  Cover                       — deal name, snapshot date, project list, status pill
2.  Underwriting Summary        — rollup KPIs + scenario S&U + per-project mini-summary
3.  Underwriting Pro Forma      — annual P&L summed across projects
4.  Underwriting Cash Flow      — annual levered + unlevered, scenario total
5.  Investor Returns            — waterfall distributions (LP IRR/EM, GP promote)
6.  Assumptions                 — single sheet, sectioned (see §4)
7.  P1 {Project Name}           — per-project pro forma + cash flow + S&U
8.  P2 {Project Name}
…   (one sheet per project, max 5 projects per Scenario)
N.  Glossary & Methodology      — final sheet (definitions + which engine writes each metric)
```

Sheet-name format: `P1 Liberty`, `P2 East 25`. Prefix is exactly 4 chars
(`P` + 1- or 2-digit ordinal + space). **Project name truncated to 27 chars**
so the full sheet name fits Excel's 31-char limit (4 + 27 = 31). Trailing
whitespace stripped after truncation. `max_projects_per_scenario = 5` is
enforced upstream, so we never need a 3-digit ordinal.

---

## 3. Sheet Contents (high-level)

### 3.1 Cover

| Row | Field | Source |
|---|---|---|
| Title | `<Deal name> — <Scenario name>` | `Deal.name`, `Scenario.name` |
| Subtitle | "Snapshot as of {now} PT" | `datetime.now()` |
| Sponsor | `Organization.name` | via `Deal.org_id` |
| Project count | n | `len(deal_projects)` |
| Project list | bullets, one per project | `deal_projects` |
| Status | text version of [`_compute_calc_status`](../../app/api/routers/ui.py) overall verdict | reuse helper |

Logo / branding skipped. Single sheet, no scrollable data.

### 3.2 Underwriting Summary

Hero KPI block (top, 2-column key/value grid, gold accent on values):

- Total Project Cost
- Equity Required
- Stabilized NOI (combined)
- Stabilized DSCR (worst project, since DSCR is per-loan)
- Combined Levered IRR
- Combined Equity Multiple
- Hold period (months, from longest project)
- Source: `rollup_summary` + `rollup_irr` (in
  [`app/engines/underwriting_rollup.py`](../../app/engines/underwriting_rollup.py))

Sources & Uses table (full scenario, not per-project):

- Uses: sum across projects, by phase
- Sources: scenario `CapitalModule` rows (deduplicated for shared modules — query
  via [`is_shared_source`](../../app/engines/cashflow.py) at cashflow.py:846)
- Sources = Uses delta line at bottom

Per-project mini-summary table:

- One row per project: name, TPC, Equity, NOI, DSCR, IRR. Values link to that
  project's sheet via `=HYPERLINK("#'P1 Liberty'!A1", ...)` — Excel resolves
  the `#'<sheet>'!<cell>` syntax to in-workbook navigation.

### 3.3 Underwriting Pro Forma (annual)

- Columns: **Y0 (essential — acquisition close), Y1, Y2 … Y10**.
  Y0 is required because multi-project deals routinely have acquisition
  outflows and partial-year operations in different projects' Y0 windows
  that wouldn't be visible if Y0 were rolled into Y1.
- Rows: Gross Rev, Vacancy, EGI, OpEx (one row per category — `Real Estate Taxes`,
  `Insurance`, etc., summed across projects), NOI, CapEx Reserve, Replacement
  Reserve, Stabilized NOI line bolded with accounting underline.
- Source: monthly `CashFlowLineItem` aggregated to annual via the helper below.

### 3.4 Underwriting Cash Flow (annual)

- Columns: **Y0 … Y10** (or to longest project's exit, whichever later)
- Rows: NOI, Capital Events (acquisition + exit), Levered Cash Flow,
  Unlevered Cash Flow, Debt Service, DSCR, Cumulative LCF.
- Source: aggregated `CashFlow` (scenario-wide, summed across projects).
- Y0 holds acquisition capital events for any project that closes in
  period 0, even if other projects don't begin until later.

### 3.5 Investor Returns

- Waterfall by tier (Pref → Catchup → Promote tiers)
- Per-tier columns: LP CF, GP CF, LP IRR-to-tier, LP CoC
- Final row: total LP IRR, LP EM, GP IRR, GP promote $.
- Source: `WaterfallResult` rows aggregated via `rollup_waterfall`.

### 3.6 Assumptions (single sheet, sectioned)

Confirmed: one sheet, three blocks stacked:

```
Block A — Scenario-level (rows 1-25)
  Sponsor / Org name
  Hold period (years)
  Discount rate
  Exit cap rate
  Income mode (NOI vs Revenue/OpEx)
  Debt structure
  Reserve policies (operating reserve months, etc.)
  Source: Scenario.* + OperationalInputs (default project's, since these are
  scenario-level conceptually)

Block B — Per-project (rows 27 onward)
  Columns: Concept | P1 | P2 | P3 | P4 | P5
  Rows:    Acquisition price, Unit count, Avg in-place rent, Stabilized vacancy,
           OpEx growth, Renovation cost / unit, Stabilized rent, Lease-up months,
           Construction months, etc.
  Source: per-project OperationalInputs + UnitMix + UseLines.

Block C — Capital stack (rows below B)
  Columns: Module label | Funder type | Principal | Rate | Term | LTV | DSCR cap | Active phases
  One row per scenario CapitalModule. Indicates "shared" if junction count > 1.
  Source: CapitalModule + CapitalModuleProject junction.
```

### 3.7 Per-Project Sheets (`P{n} {Name}`)

Same layout for every project, in this order:

1. Project header (name, location, deal type, project status pill)
2. Project Pro Forma (annual, same columns as 3.3)
3. Project Cash Flow (annual, same as 3.4)
4. Project S&U table (uses + sources from junction-scoped principal)

Hyperlinks at top: `← Underwriting Summary` and `Glossary →`.

### 3.8 Glossary & Methodology (last sheet)

**Doc-driven, validated bidirectionally.** Content is parsed at build time
from [`docs/FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md). The parser walks
markdown headers + paragraphs and extracts
`(term, audience, definition, calc_method, source_section)` for every
documented metric.

Columns rendered on the sheet:

- **Term** — e.g., "DSCR"
- **Definition** — first paragraph following the header
- **Calculation** — code-block immediately under the header (if present)
- **Reference** — section anchor like `FINANCIAL_MODEL.md#dscr`

**Audience tagging convention** (added during doc refactor — see §11):

```
## DSCR  [investor, app]

Definition paragraph here…
```

Each metric header in `FINANCIAL_MODEL.md` carries a bracketed
audience tag. Allowed tags:

- `investor` — appears in the Investor Export glossary
- `app` — used inside the web app's UI (status pills, tooltips, modals)
- `internal` — engine-only, not user-facing

Most entries will be `[investor, app]`. The parser only emits glossary
rows for headers that include `investor`. Headers tagged `[app]` or
`[internal]` exclusively are skipped.

**Bidirectional data-quality contract** (this is what the exporter
guarantees and what the test in §7 enforces):

1. Every metric used in the workbook (every `s_*` / `p<n>_*` / `r_*`
   named range) **must** trace to a doc entry tagged `investor`.
2. Every doc entry tagged `investor` **must** appear in the workbook
   (as a named range *or* as an explicit "covered by row …" line in
   the glossary, when the metric only shows up as a row label rather
   than a discrete cell).

A mismatch in either direction is a **test failure**, not a warning,
not a placeholder row. Build the export → run the validator → fail CI
if anything's out of sync. This keeps the math doc and the investor
artifact provably aligned.

---

## 4. Named Range Convention (final)

**Underscore prefixes**, lowercase, snake_case.

| Prefix | Meaning | Example |
|---|---|---|
| `s_` | scenario-level scalar | `s_cap_rate`, `s_hold_years`, `s_exit_cap` |
| `p<n>_` | per-project scalar (1-based ordinal) | `p1_acquisition_price`, `p2_stabilized_noi` |
| `r_` | range (multi-cell) | `r_uw_noi_y1_y10`, `r_p1_revenue_y1_y10` |

Rules:

1. **Workbook-scoped, absolute references** — every defined name resolves to
   `=Sheet!$C$5` style. Cross-sheet formulas in Phase 2 won't need
   `'Sheet'!` prefixes.
2. **One name = one contiguous range.** No discontiguous unions.
3. **Lowercase only** in code. (Excel is case-insensitive for name resolution
   but case-preserving in display, so consistency matters.)
4. **Underscore over period** — period-style (`s.cap_rate`) is rejected by
   older Excel and breaks `defined_names` lookup in some `openpyxl` versions.
   Underscore is safe, lower-effort, equally readable.

Why this is "lower effort, higher quality":

- No need to escape names anywhere.
- Survives copy/paste between workbooks (Excel rewrites `'Sheet'!` refs but
  leaves named ranges intact).
- Phase 2 formulas read like English: `=s_cap_rate * s_year_10_noi`.

---

## 5. Code Structure

### 5.1 New file

`app/exporters/investor_export.py` — single public async function:

```python
async def export_investor_workbook(
    deal_model_id: UUID, session: AsyncSession
) -> bytes:
    ...
```

Returns workbook bytes ready for `Response`. ~700-900 lines projected. Style
follows the existing exporter ([`excel_export.py`](../../app/exporters/excel_export.py))
for value coercion (`_to_v` helper) and column-width handling but everything
else is fresh — different file because the audiences and structures diverge.

### 5.2 Helper module

`app/exporters/_workbook_helpers.py` — shared utilities:

- `CellRegistry` class (see §6)
- `BRAND` palette dict (navy `#0D1B2A`, slate `#415A77`, gold `#C9A96E`, etc.)
- `header_row(ws, row, columns)`, `section_label(ws, row, text)`, `kv_row(ws, row, key, value, name)`
- `accounting_format`, `pct_format`, `int_format`, `multiple_format` constants
- `freeze_top(ws, row=2)`, `set_widths(ws, widths)`, `print_landscape(ws)`

Both exporters can use these eventually; for now only `investor_export.py`
imports them. The round-trip exporter stays untouched.

### 5.3 Aggregation helpers (live inside `investor_export.py`)

```python
def _aggregate_annual(monthly_rows: list[CashFlow]) -> dict[int, dict]: ...
def _annual_line_items(items: list[CashFlowLineItem]) -> dict[int, dict[str, Decimal]]: ...
def _waterfall_by_tier(results: list[WaterfallResult]) -> dict[str, list[Decimal]]: ...
```

Year mapping convention: `year = 0 if period == 0 else (period - 1) // 12 + 1`.
Period 0 = acquisition close (Y0); periods 1-12 = Y1; etc.

### 5.4 Sheet builders (also in `investor_export.py`)

One per sheet, all take `(wb, registry, ctx)` where `ctx` is a frozen dict of
loaded data:

```python
def _build_cover(wb, reg, ctx): ...
def _build_uw_summary(wb, reg, ctx): ...
def _build_uw_proforma(wb, reg, ctx): ...
def _build_uw_cashflow(wb, reg, ctx): ...
def _build_investor_returns(wb, reg, ctx): ...
def _build_assumptions(wb, reg, ctx): ...
def _build_project_sheet(wb, reg, ctx, project_idx, project): ...
def _build_glossary(wb, reg, ctx): ...
```

`ctx` shape (built by `_load_all` analogous to the existing exporter at
[excel_export.py:124](../../app/exporters/excel_export.py)):

```python
{
  "deal": Deal, "scenario": Scenario, "org": Organization,
  "projects": list[Project],                       # ordered by created_at
  "operational_inputs": dict[UUID, OperationalInputs],   # by project_id
  "outputs": dict[UUID, OperationalOutputs],
  "use_lines": dict[UUID, list[UseLine]],
  "income_streams": dict[UUID, list[IncomeStream]],
  "expense_lines": dict[UUID, list[OperatingExpenseLine]],
  "unit_mix": dict[UUID, list[UnitMix]],
  "milestones": dict[UUID, list[Milestone]],
  "cash_flows": dict[UUID, list[CashFlow]],        # per project
  "cash_flow_items": dict[UUID, list[CashFlowLineItem]],
  "capital_modules": list[CapitalModule],          # scenario-wide
  "junctions": list[CapitalModuleProject],
  "waterfall_tiers": list[WaterfallTier],
  "waterfall_results": list[WaterfallResult],
  "rollup": dict,    # output of rollup_summary + rollup_irr + rollup_waterfall
}
```

### 5.5 Route

Add to [`app/api/routers/ui.py`](../../app/api/routers/ui.py) alongside the
existing export route. Endpoint:

```
GET /ui/models/{model_id}/investor-export.xlsx
```

Returns `Response(content=..., media_type="application/vnd.openxmlformats-...")`
with `Content-Disposition: attachment; filename="<deal>-<scenario>-investor.xlsx"`.

UI hook: add a button next to the existing "Export Excel" in
`app/templates/model_builder.html`. Label: "Investor Export". Place it on the
top toolbar so it's reachable from every module.

---

## 6. CellRegistry Pattern

```python
@dataclass
class CellAddress:
    sheet: str
    row: int          # 1-based
    col: int          # 1-based
    end_row: int | None = None   # set for ranges
    end_col: int | None = None

class CellRegistry:
    def __init__(self):
        self._names: dict[str, CellAddress] = {}

    def write(self, ws, row, col, value, *, name=None, fmt=None, **style):
        ws.cell(row=row, column=col, value=value)
        if fmt: ws.cell(row=row, column=col).number_format = fmt
        # ...apply style...
        if name:
            self.register(name, ws.title, row, col)

    def register_range(self, name, sheet, top_row, bottom_row, col):
        self._names[name] = CellAddress(sheet, top_row, col, bottom_row, col)

    def register(self, name, sheet, row, col):
        if name in self._names:
            raise ValueError(f"defined name {name!r} already registered "
                             f"to {self._names[name]}")
        self._names[name] = CellAddress(sheet, row, col)

    def emit(self, wb):
        from openpyxl.workbook.defined_name import DefinedName
        for name, addr in self._names.items():
            ref = f"'{addr.sheet}'!${get_column_letter(addr.col)}${addr.row}"
            if addr.end_row:
                ref += f":${get_column_letter(addr.end_col or addr.col)}${addr.end_row}"
            wb.defined_names[name] = DefinedName(name=name, attr_text=ref)
```

**Discipline:** every cell that is investor-meaningful gets a name. Cells that
are pure presentation (section dividers, headers) don't. Aim for ~300 names
in a typical 2-project workbook.

---

## 7. Tests

New file: `tests/exporters/test_investor_export.py`.

**Smoke tests** (must pass):

- `test_workbook_has_expected_sheets` — load tiny seeded scenario, export,
  assert sheet names + order match §2 exactly.
- `test_named_ranges_resolve_to_existing_cells` — for every defined name, open
  the workbook in `data_only=False` mode, walk to `Sheet!Cell`, assert it has
  a value.
- `test_sheet_protection_unset` — investor export is read-only by convention
  (no `_setup` round-trip sheet); assert no sheets are password-protected so
  the LP can copy values out.
- `test_per_project_sheet_per_project` — fixture with 2 projects → 2 `P{n}`
  sheets; with 1 project → 1 sheet, no orphan placeholders.
- `test_long_project_name_truncated_to_27_chars` — 60-char project name →
  sheet name `P1 ` + first 27 chars.

**Doc / Export parity tests** (must pass, enforce §3.8 contract):

- `test_every_named_range_has_doc_entry` — for every named range matching
  `^(s|p\d+|r)_` in the exported workbook, look up the corresponding metric
  in `FINANCIAL_MODEL.md`, assert it exists and is tagged `investor`. Fails
  with a precise list of orphan named ranges.
- `test_every_investor_doc_entry_appears_in_export` — for every header in
  `FINANCIAL_MODEL.md` tagged `investor`, assert it appears in the workbook
  either as a named range or as a row label on a Pro Forma / Cash Flow /
  Investor Returns sheet (lookup by exact term or registered alias). Fails
  with a list of doc entries missing from the export.
- `test_audience_tags_well_formed` — parses `FINANCIAL_MODEL.md`, asserts
  every metric header carries one of `[investor, …]`, `[app, …]`, or
  `[internal]`. Untagged headers fail the test (forces the doc author to
  decide audience explicitly).

**Parity test** (compute-side, optional):

- `test_uw_summary_irr_matches_engine_output` — compute via engine, compare
  cell value for `s_combined_irr`. Tolerance 0.01%. Same idea for
  `s_total_project_cost`.

Reference for fixture seeding: `tests/conftest.py` already has
`seed_deal_model_with_financials()`; reuse.

---

## 8. Build Order (5 commits)

### Commit 0 — Math doc refactor + validator (prerequisite)
See §11 in full. Lands before commit 1.
- Restructure `FINANCIAL_MODEL.md` into per-metric `##`/`###` headers with
  `[audience]` tags and labelled bodies.
- New `app/exporters/_doc_validator.py` parser.
- New `tests/exporters/test_financial_model_md.py` — fails CI if any
  header is malformed or untagged.
- Round-trip exporter docstring gets a deprecation notice (no behaviour
  change yet).

### Commit 1 — Skeleton + Cover + Assumptions + Glossary
~300 lines.
- `_workbook_helpers.py` with `CellRegistry`, palette, format helpers
- `investor_export.py` with `_load_all`, `_build_cover`, `_build_assumptions`,
  `_build_glossary` (sources from `_doc_validator`), `export_investor_workbook`
  orchestrator
- Route + new UI button (replacing the round-trip "Export Excel" button)
- Smoke tests for sheet order + named-range emission
- **Bidirectional doc/export validation tests** wired up — they have nothing
  to validate yet beyond the glossary, but they run and pass.

### Commit 2 — Underwriting rollup sheets
~400 lines added to `investor_export.py`.
- `_aggregate_annual`, `_annual_line_items`, `_waterfall_by_tier` helpers
- `_build_uw_summary`, `_build_uw_proforma`, `_build_uw_cashflow`,
  `_build_investor_returns`
- Compute-side parity tests + the §7 doc-validation tests now exercise
  every named range introduced.

### Commit 3 — Per-project sheets
~150 lines.
- `_build_project_sheet(wb, reg, ctx, project_idx, project)` + ordinal-aware
  named-range emission (`p{n}_*`)
- Hyperlink wiring on Underwriting Summary's per-project mini-table
- Tests for multi-project fixture
- Final pass on the validation tests — every `p<n>_*` named range traces
  back to a doc entry tagged `investor`.

Each commit ships independently. Commit 0 makes the math doc trustworthy.
After commit 1, the workbook exists as an audit document with cover,
assumptions, and glossary. After commit 2, it's investor-presentable for
single-project deals. Commit 3 unlocks multi-project.

### Commit 4 — Post-refactor patch (lands after the opportunities/buildings refactor)
Triggered by the schema work in
[`opportunities-buildings-refactor.md`](./opportunities-buildings-refactor.md).
This commit is small (~50 LOC) and isolated — it updates only the
data-load and assumptions-sheet code, not the workbook structure or
named-range layout.

Touchpoints (all in `app/exporters/investor_export.py` unless noted):

1. **`_load_all` / `ctx` shape — `unit_mix`.** Today's `ctx["unit_mix"]: dict[UUID, list[UnitMix]]` is loaded from the standalone `unit_mix` table (rows joined by `project_id`). After the refactor, `unit_mix` is a JSONB array on `Project`. Update the loader to read `project.unit_mix` directly and validate via the Pydantic schema in `app/schemas/unit_mix.py`. Type signature becomes `dict[UUID, list[UnitMixItem]]` where `UnitMixItem` is the Pydantic model.

2. **Assumptions sheet, Block B — acquisition price.** The "Acquisition price" row currently sources from the seeded value carried via the opportunity wizard. After the refactor, it reads `Project.acquisition_price` directly (a real persisted column). Replace the lookup; the named range (`p<n>_acquisition_price`) and cell address don't change.

3. **Assumptions sheet, Block B — unit-derived rows.** "Unit count," "Avg in-place rent," "Stabilized rent," etc., are computed from unit_mix. With the JSONB shape, swap the row-iterator for a list-comprehension over `project.unit_mix`. Output rows and named ranges are unchanged.

4. **Per-project sheet header — deal_type → proposed_use.** The header cell labelled "Deal Type" currently reads `Project.deal_type` (untyped string). After the refactor, that column is removed. Replace with two cells: "Property Type" sourced from `project.opportunity.project_type` (lineage FK; the property's current type) and "Proposed Use" sourced from `project.proposed_use` (the deal's plan). Add named ranges `p<n>_property_type` and `p<n>_proposed_use`. Update `FINANCIAL_MODEL.md` glossary entries to add these as `[investor, app]` tagged metrics so the bidirectional validator stays green.

5. **`FINANCIAL_MODEL.md` updates.** Any glossary entries that reference the dropped `deal_type` field are renamed/retagged in the same commit. The bidirectional validator (commit 0's deliverable) will fail CI on drift, which is the expected forcing function.

6. **Tests.** Update `tests/conftest.py` `seed_deal_model_with_financials()` to populate the new fields. Update fixture-driven test expectations in `tests/exporters/test_investor_export.py`. The bidirectional doc/export validator tests (§7) catch any missed touchpoints automatically.

This commit is the export's only direct dependency on the schema refactor;
all other commits are refactor-blind and stable.

---

## 9. References (existing code & data)

| Need | Where |
|---|---|
| Round-trip exporter to mirror style for utilities | [`app/exporters/excel_export.py`](../../app/exporters/excel_export.py) |
| Rollup data sources | [`app/engines/underwriting_rollup.py`](../../app/engines/underwriting_rollup.py) |
| Cashflow + line items | [`app/engines/cashflow.py`](../../app/engines/cashflow.py), `CashFlow` + `CashFlowLineItem` models in [`app/models/cashflow.py`](../../app/models/cashflow.py) |
| Waterfall results | [`app/engines/waterfall.py`](../../app/engines/waterfall.py), `WaterfallResult` model |
| Capital stack + junction | `CapitalModule` + `CapitalModuleProject` in [`app/models/capital.py`](../../app/models/capital.py); `is_shared_source()` helper at cashflow.py:846 |
| Status pill text | `_compute_calc_status` in [`app/api/routers/ui.py`](../../app/api/routers/ui.py) |
| Math glossary content | [`docs/FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md) |
| Reference investor templates | `docs/models/HelloData MultiFamily Model.xlsx`, `docs/models/Original-Apartment-Acquisition-Model-v2.41-3ylxhk.xlsx` (~250 named ranges, snake_case — exemplar) |
| Existing v1 plan (now superseded) | [`docs/feature-plans/investor-excel-export.md`](./investor-excel-export.md) |
| Schema refactor that triggers commit 4 | [`docs/feature-plans/opportunities-buildings-refactor.md`](./opportunities-buildings-refactor.md) |
| Test fixture helpers | `tests/conftest.py` — `seed_deal_model_with_financials` |
| Existing test layout | [`tests/exporters/test_benchmark_fixtures.py`](../../tests/exporters/test_benchmark_fixtures.py) |

---

## 10. Open Items for the Executor

- The existing v1 plan in `investor-excel-export.md` should be marked
  superseded but **not deleted** — it captures Phase 2/3 thinking (formula
  template + parity QA) that will guide future work.
- Investor export is **read-only by convention** — no Protection() locking
  (LPs need to copy values out).
- Decision on print scaling deferred — agent can default to "Fit to 1 page
  wide" on summary sheets and revisit if user asks.
- No icons / images in this build. Clean text-only is faster and cleaner than
  half-baked branding.

### Round-trip exporter deprecation

The round-trip exporter at `app/exporters/excel_export.py` is **deprecated**
as of this build. Concrete steps:

1. Add a deprecation notice at the top of the module's docstring pointing
   to this plan and the new investor export.
2. Replace the existing UI button at
   [`app/templates/model_builder.html`](../../app/templates/model_builder.html)
   with the new "Investor Export" button. Do **not** ship two buttons.
3. Keep the round-trip route + tests green during the transition — it's
   our safety net while the investor export bakes — but stop adding
   features and stop accepting new sheets/columns into it.
4. Once the investor export covers all use cases (and we've confirmed no
   workflows depend on the round-trip), the route + module + tests get
   deleted in a follow-up commit. Out of scope here.

A "simplified underwriting" extract (e.g., a one-sheet summary the user
can email a broker without sending the full investor package) may live
alongside the investor export later — but it's blocked on the math doc
being trustworthy and the investor export being feature-complete first.

### Glossary / math-doc data quality

- The glossary is **doc-driven** and the export is **validated against the
  doc** in both directions (see §3.8 and §7). Doc-export drift is a test
  failure, not a warning.
- The `FINANCIAL_MODEL.md` audience-tagging refactor (§11) is a hard
  prerequisite for commit 1 of this plan. Without tags, the parser has no
  way to decide what belongs in the investor glossary vs. what's app-only
  and the bidirectional validation tests can't run.

---

## 11. Prerequisite: FINANCIAL_MODEL.md refactor

This is **commit 0** of the build sequence. Must land before commit 1.

### What changes

[`docs/FINANCIAL_MODEL.md`](../FINANCIAL_MODEL.md) (846 lines) currently
mixes engine internals, investor-facing math, and app-only helpers without
distinction. The refactor adds two structural rules:

**Rule 1 — Every metric is a level-2 (`##`) or level-3 (`###`) header
followed by a structured body:**

```markdown
## DSCR  [investor, app]

**Definition.** Debt Service Coverage Ratio = NOI ÷ Annual Debt Service.

**Calculation.**
\`\`\`
DSCR = noi_stabilized / (debt_service_monthly * 12)
\`\`\`

**Engine source.** `compute_cash_flows` writes monthly `debt_service` into
`CashFlow`; `OperationalOutputs.dscr` materializes the stabilized ratio.

**Notes / edge cases.** Lenders typically require ≥ 1.20–1.25. DSCR is
per-loan, so multi-debt scenarios surface a worst-case across modules.
```

The parser (§3.8) keys off this exact shape: header → audience tag →
labelled paragraphs.

**Rule 2 — Audience tag on every metric header.** One of:

- `[investor, app]` — investor-facing math also surfaced in the app UI
  (most common, expected ~95% of entries)
- `[investor]` — investor-only (rare; only if the metric exists for LP
  reporting but isn't shown in the web app)
- `[app]` — app-only helper (e.g., a tooltip-only derived field)
- `[internal]` — engine implementation detail not user-facing

Untagged headers fail the validation test (see §7).

### How to do the refactor

This is a content-and-structure pass, not a math correction:

1. Walk the existing 846 lines section by section. For every distinct
   metric, lift it into the standard header shape above.
2. Tag audience based on whether the metric appears (or should appear) in
   the investor export sheets defined in §3.
3. Where the existing prose covers multiple metrics in one block, split it
   into separate headers per metric.
4. **Don't change the math.** The math is the source of truth — the
   refactor is purely about making the doc machine-parseable and audience-
   classified so the export can validate against it.
5. After the refactor, run the validator standalone (no export needed):
   `python -m app.exporters._doc_validator` should print every parsed
   metric grouped by audience tag, with a non-zero exit code if any
   header is malformed or untagged.

Expected outcome: ~80–120 metric headers across the doc, ~95% tagged
`[investor, app]`, the rest split between `[app]` and `[internal]`.
Zero `[investor]`-only is fine; zero untagged is required.

### Files added during this prerequisite

- `app/exporters/_doc_validator.py` — markdown parser + validator
  (re-used by the glossary builder in commit 1).
- `tests/exporters/test_financial_model_md.py` — runs the validator on
  the live doc and fails CI if anything's malformed.
