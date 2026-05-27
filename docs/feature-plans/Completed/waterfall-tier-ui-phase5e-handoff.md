# Profit Waterfall — Work Log & Next Steps

## What Was Built (May 27, 2026)

### Commits shipped to production
- `0a1bb91` + `484118c` — **Profit Waterfall tier table** in Owners & Profit panel
- `a3a46e6` — **LP% auto-calc** in waterfall tier form

### What's live
**Owners & Profit panel** now has a "Profit Waterfall" section between DDF and Profit Metrics:
- Empty state: callout explaining auto-GP-100% behavior + "+ Add First Tier" button
- Populated state: table of WaterfallTier rows (Priority, Type, IRR Hurdle, LP %, GP %, Description)
- Clicking a row opens the edit drawer (existing form at `model_builder_line_form.html:2117`)
- "+ Add Tier" button in section header

**Waterfall tier form** (`model_builder_line_form.html`):
- GP Split field is now **readonly**, auto-fills as `100 − LP%` via JS
- Guarantees `lp_split_pct + gp_split_pct = 100` always
- LP Split field has `id="waterfall-lp-split"`, GP has `id="waterfall-gp-split"`

**ui.py query fix**: `order_by(WaterfallTier.priority, WaterfallTier.id)` — adds id tiebreaker

### How waterfall tiers work (architecture)
- Tiers are **role-based**, not per-source-vehicle
- `lp_split_pct` = % of distributable going to all LP equity collectively
- `gp_split_pct` = % going to all GP equity collectively (auto = 100 − LP)
- Engine distributes LP's share proportionally across LP source vehicles by invested amount
- `capital_module_id` is NULL on equity tiers (debt service tiers link to specific debt modules)
- Auto-generated tiers (when no user tiers exist): debt_service per debt module + residual 100% GP

### WaterfallTierType enum values
`debt_service` | `pref_return` | `return_of_equity` | `catch_up` | `irr_hurdle_split` | `deferred_developer_fee` | `residual`

---

## What Still Needs to Be Done — Excel Export Side (Phase 5e)

### The gap
LP/GP **IRR cells** in the export workbook still show em-dashes. LP **Equity Multiple** (`lp_em`) does populate correctly because its formula references `s_lp_distributions_total` and `s_committed_lp_equity` — both already written.

LP/GP IRR requires the engine to write a **per-class cash-flow series** — a column of period-level net cash flows for LP separately and GP separately — so the Excel `IRR()` or `XIRR()` formula has data to compute from.

### What the exporter already has (Phase 5d baseline)
- Named ranges `s_lp_distributions_total` and `s_committed_lp_equity` → EM formula works
- LP/GP waterfall result rows exist in `WaterfallResult` table after `compute_waterfall()` runs
- Excel export lives in `app/exporters/` — likely `excel.py` or similar

### What Phase 5e needs to add
1. **Engine**: after `compute_waterfall()`, aggregate per-period LP net cash flows:
   - LP cash flow per period = LP distributions received − LP capital called
   - Write as a series (one value per month or per year) to a named range or hidden column
   - Same for GP
2. **Exporter**: wire those series into IRR/XIRR formula cells in the workbook
   - Named ranges probably: `lp_cf_series` / `gp_cf_series` (or period columns)
   - IRR cell formula: `=XIRR(lp_cf_series, date_series)`

### Key files to look at
| File | Purpose |
|---|---|
| `app/engines/waterfall.py` | Waterfall engine — `compute_waterfall()`, `WaterfallResult` writes |
| `app/exporters/` | Excel export — find the file that builds the investor returns sheet |
| `app/models/capital.py` | `WaterfallResult` model — what per-period data is already stored |
| `docs/FINANCIAL_MODEL.md` | Named range reference for Phase 5d cells already wired |

### Suggested first step for next agent
1. Read `app/engines/waterfall.py` — find where `WaterfallResult` rows are written, what fields exist (`tier_id`, `period`, `lp_distributed`, `gp_distributed`, etc.)
2. Read the Excel exporter — find the investor returns sheet builder, see which named ranges are already written vs still em-dashes
3. Check `docs/FINANCIAL_MODEL.md` for Phase 5 named range map
4. Then build the per-period LP/GP CF aggregation and wire the XIRR cells
