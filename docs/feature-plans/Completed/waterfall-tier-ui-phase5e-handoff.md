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

## Excel Export Status — All Done

Phases 5d, 5e, 5f, 5g all shipped as of May 27, 2026.

| Named range | Status |
|---|---|
| `s_lp_distributions_total` / `s_gp_distributions_total` | ✅ live |
| `s_committed_lp_equity` / `s_committed_gp_equity` | ✅ live |
| `s_lp_em` / `s_gp_em` | ✅ live (formula cells) |
| `s_lp_coc_y1` / `s_gp_coc_y1` | ✅ live (formula cells) |
| `r_returns_lp_cf` / `r_returns_gp_cf` | ✅ live (annual CF series rows) |
| `r_returns_cf_dates` | ✅ live (shared date series) |
| `s_lp_irr` / `s_gp_irr` | ✅ live — `=IFERROR(XIRR(r_returns_lp_cf, r_returns_cf_dates), fallback)` |

Key commits: `c2801f1` (Phase 5g — XIRR), `bc041e5` (docs). Both in VM 114 HEAD as of this session.

## All Items Complete

Sensitivity sheet writes static engine-computed values at export time with note: *"For reference only. Changes to Excel Report do not update Sensitivity Data Table."* Dynamic `TABLE()` formula approach was abandoned — static values are sufficient and the disclaimer makes the limitation clear. `3ff3032`.
