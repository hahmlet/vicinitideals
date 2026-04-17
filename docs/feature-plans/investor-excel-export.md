# Investor-Ready Excel Export

**Status**: Planned (not yet started)
**Last updated**: 2026-04-16
**Depends on**: HelloData model parity engine changes (completed 2026-04-16)

---

## Context

We completed a HelloData MultiFamily Model comparison and closed several engine gaps (dual-constraint sizing, refi, bad debt/concessions, renovation absorption, prepay penalty, AM fee). The reference model is saved at `docs/models/HelloData MultiFamily Model.xlsx`.

The next step is a single-button export that produces a professional, investor-ready spreadsheet from any Deal. This is separate from the existing round-trip `excel_export.py` which is designed for editing and re-import, not investor presentation.

---

## Phased Approach

### Phase 1: Values-Only Export (build first, stay here longer than you think)

A professionally formatted workbook populated with computed values from our engines. **Zero maintenance on engine logic changes** — recompute, re-export, done.

This is what 90% of LP investors actually want: clear numbers, clean formatting, auditable assumptions. Investors who want to tweak assumptions get a sensitivity table (already in the engine) or the round-trip export.

### Phase 2: Formula Template (future, when demand warrants)

Instead of generating formulas in Python, maintain an `.xlsx` template with formulas already in place. The engine populates assumption cells; formulas reference those cells. Logic changes only require updating the template, not Python code. This is how ARGUS and most institutional platforms work.

**UX challenge**: Not all assumptions are investor-facing. A deal might have 200+ parameters but an investor only wants to adjust 10-15 (cap rate, exit cap, rent growth, vacancy, hold period, LTV, rate). The template needs a clean "Assumptions" sheet with the adjustable inputs front-and-center, and a hidden "Engine Data" sheet with everything else. The formulas on the Pro Forma sheet reference the visible assumptions for the tunable ones and the hidden sheet for the rest.

**Design principle**: The visible assumptions sheet should mirror what HelloData shows (rows 7-22 of their model) — roughly 15-20 inputs that an investor would actually change. Everything else is locked/hidden but still feeds the formulas.

### Phase 3: Automated QA (future, required before Phase 2 ships)

Run both engines (Python + Excel), compare outputs cell-by-cell, flag divergence. The CellRegistry from Phase 1 enables this — every value written has a logical key mapped to a cell coordinate.

---

## Files to Create

### `app/exporters/investor_export.py` (~700-900 lines)
Single public async function: `export_investor_workbook(deal_model_id, session) -> bytes`

---

## Files to Modify

| File | Change | Location |
|---|---|---|
| `app/api/routers/ui.py` | New route: `GET /ui/models/{model_id}/investor-export.xlsx` | After line 6543 |
| `app/templates/model_builder.html` | New button: "Investor Model" (btn-primary) | After line 457 |

---

## Data Loading

Reuse the pattern from `excel_export.py:_load_all()` plus:
- `CashFlowLineItem` rows (per-stream income and per-expense detail)
- `WaterfallResult` rows (per-tier, per-investor distributions)

All data already exists in computed tables — no new engine work needed.

### Monthly-to-Annual Aggregation

`_aggregate_annual()` groups monthly CashFlow + CashFlowLineItem + WaterfallResult rows into annual buckets. Year mapping: `year = 0 if period == 0 else (period - 1) // 12 + 1`.

Each `AnnualBucket` contains:
- Summed CashFlow fields (gross_revenue, vacancy, EGI, opex, capex, NOI, debt_service, NCF)
- `income_by_label` and `expense_by_label` dicts from CashFlowLineItem
- `capital_events` dict from CashFlowLineItem
- Waterfall distributions by tier and module

---

## Sheet Layout (6 sheets)

### 1. Executive Summary
One-page investor snapshot. ~45 rows, 8 columns.
- Investment Returns: LP IRR, LP EM, LP CoC Y1, GP IRR, Project IRR
- Key Metrics: purchase price, price/unit, units, cap rates, hold period
- Operating Summary: stabilized NOI, cap rate on cost, DSCR
- Sources of Capital table (per CapitalModule)
- Uses of Capital table (per UseLine, grouped by phase)

### 2. Pro Forma
Annual P&L. Dynamic row count. Columns = Year 1 through Year N.
- Income section: one row per IncomeStream, total GPR, vacancy/bad debt/concessions, EGI
- Expense section: one row per OperatingExpenseLine, total OpEx, CapEx reserve, OpEx ratio
- NOI line (bold, accounting underline)

### 3. Cash Flow Analysis
Leveraged and unleveraged CF. Columns = Year 0 through Year N.
- Unleveraged: NOI + capital events + disposition = unleveraged NCF
- Leveraged: NOI - debt service (per module) + financing/refi + disposition = leveraged NCF
- Metrics: DSCR and debt yield per year

### 4. Investor Returns
Waterfall distributions. Columns = Year 0 through Year N.
- Waterfall structure table (static: tier, type, LP%, GP%, hurdle)
- Partnership CF: leveraged CF - AM fee = distributable
- Per-tier distributions (LP line + GP line per tier)
- Summary: LP total, GP total, combined
- Return metrics: IRR, EM, CoC

### 5. Sources & Uses
Capital stack detail. Static table.
- Sources per CapitalModule: type, amount, %, rate, IO, amort, term
- Uses per UseLine: label, phase, amount, %
- Reconciliation: Sources - Uses

### 6. Assumptions
All input parameters for audit. Key-value format.
- Deal info, acquisition, timeline, income streams, expense lines, financing per module, exit, waterfall tiers, export metadata

---

## Styling

Professional CRE palette (distinct from round-trip export):

| Element | Background | Font |
|---|---|---|
| Sheet title | #0D1B2A deep navy | Calibri 16pt bold white |
| Section header | #1B2838 steel | Calibri 12pt bold white |
| Sub-header | #415A77 slate | Calibri 10pt bold white |
| Data rows | white / #F7F7F7 alternating | Calibri 10pt |
| Totals | top border (accounting line) | Calibri 10pt bold |
| KPI values | — | Calibri 14pt bold #C9A96E gold |

Number formats: `$#,##0` (currency), `0.00%` (rates), `0.00x` (multiples), `#,##0` (integers).

All sheets: frozen panes, print area set (landscape, fit-to-1-page-wide), protected (no password).

---

## Phase 2 Prep (built into Phase 1)

### CellRegistry
Every value write records `{logical_key: "SheetName!C14"}`. Makes formula replacement and automated QA trivial later.

### Deterministic row ordering
Income streams, expense lines, and waterfall tiers always written in the same order (sorted by label / priority). Stable positions for formula references.

### Template-friendly assumption layout
The Assumptions sheet groups investor-adjustable inputs (cap rate, exit cap, rent growth, vacancy, hold period, LTV, rate — roughly 15-20 fields) separately from engine internals. In Phase 2, the adjustable section becomes the "unlocked" input area; everything else stays hidden/locked.

---

## Implementation Sequence (when ready to build)

1. Create `investor_export.py`: constants, CellRegistry, style helpers, data loader, annual aggregation
2. Build sheets: Executive Summary → Pro Forma → Cash Flow → Sources & Uses → Assumptions → Investor Returns
3. Add route to `ui.py` and button to `model_builder.html`
4. Test with existing deals, handle edge cases (no cashflows, no waterfall, zero streams)

---

## Edge Cases

- **No computed cash flows**: Show Executive Summary + Assumptions only, with note "Run Compute to generate full pro forma"
- **No waterfall**: Skip Investor Returns sheet or show placeholder
- **Zero income streams**: Show "No income streams configured" in Pro Forma
- **No debt**: Show "All equity deal" in Cash Flow Analysis
- **Hold period > 10 years**: Columns scale automatically; add print scaling note
- **Partial final year**: Label as "Year N (partial)"

---

## Verification

1. Click "Investor Model" on a deal with computed cashflows + waterfall
2. Verify: 6 sheets, correct year columns, NOI consistency across sheets, S=U balance, IRR matches, formatting correct
3. Open HelloData model side-by-side — verify comparable professionalism
4. Lint: `uv run ruff check app/exporters/investor_export.py`
5. Edge case: deal with no waterfall computed — graceful degradation
