# QA Test Matrix — Core Financial Flows

This document is the `REAL-37` reference matrix for automated QA coverage of the core underwriting engine.

> **Important:** passing tests are a promotion gate, not a substitute for manual backtesting. Any math-heavy change still requires a human spot-check before moving beyond review.

---

## Scope

The matrix focuses on the financial paths that most directly affect underwriting decisions:

1. **Core projections / cash flow generation**
2. **Waterfall math and capital-stack distribution**
3. **Investor reporting outputs**
4. **Regression parity against committed benchmark fixtures**

It intentionally excludes parcel lookup and scraper ingestion except where those paths validate the financial contract.

---

## Fresh Verification Evidence

| Command | Result |
| --- | --- |
| `python -m pytest tests/engines/test_cashflow.py tests/engines/test_waterfall.py tests/exporters/test_benchmark_fixtures.py tests/scripts/test_tower_ap_parity.py -q` | `10 passed, 1 skipped in 7.69s` |
| `python -m pytest tests/api/test_routers.py -k "waterfall_report or scenario or project_summary or portfolio_gantt" -q` | `11 passed, 32 deselected in 4.03s` |
| `python -m pytest tests/ -q` | `136 passed, 1 skipped in 25.79s` |

---

## Coverage Snapshot

| Area | Primary files | What is being guarded |
| --- | --- | --- |
| Core projections | `tests/engines/test_cashflow.py` | phase sequencing, milestone-date overrides, fallback month logic, itemized operating expenses |
| Waterfall math | `tests/engines/test_waterfall.py` | debt-service tiers, IRR hurdle gating, persisted `WaterfallResult` rows, levered metric recompute |
| Investor reporting | `tests/api/test_routers.py`, `tests/contract/test_compute_contracts.py` | waterfall report payloads, investor timelines, summary rollups, non-null compute outputs |
| Import / export / parity | `tests/exporters/test_benchmark_fixtures.py`, `tests/scripts/test_tower_ap_parity.py` | Excel-style benchmark parity, drift protection, portable JSON round-trips |
| Scenario regression | `tests/tasks/test_scenario.py`, `tests/api/test_routers.py` | multi-run persistence, comparison contracts, invalid-range protection |

---

## Flow-to-Test Matrix

| Financial flow | Why it matters | Automated coverage | Pass condition |
| --- | --- | --- | --- |
| **Projection engine** | Drives NOI, total timeline, exit timing, and downstream metrics | `test_build_phase_plan_*`, `test_compute_period_includes_itemized_operating_expense_lines`, benchmark fixture recompute | cash-flow rows persist, milestone logic stays stable, outputs remain within tolerance |
| **Waterfall distribution** | Determines debt service, equity return, residual split, and levered IRR | `test_compute_waterfall_persists_results_and_metrics`, `test_irr_hurdle_split_waits_until_lp_hurdle_is_met`, fixture waterfall checks | tier ordering and cumulative distributions remain correct |
| **Investor reporting** | Surfaces investor-facing timelines and summary KPIs | `test_get_waterfall_report_returns_investor_timelines_and_summary`, compute contract coverage | report response is populated and math stays aligned to waterfall rows |
| **Scenario comparison** | Supports what-if analysis and attribution deltas | scenario status / compare API tests plus `tests/tasks/test_scenario.py` | baseline vs changed cases return stable delta and attribution payloads |
| **Regression parity** | Prevents silent model drift against benchmark deals | `test_benchmark_fixtures_validate_and_recompute_expected_metrics`, `test_excel_parity_fixtures_match_first_four_years_of_cash_flow_cells`, `test_tower_ap_formulas_parity_validates_excel_targets` | summary metrics and parity windows stay inside documented tolerances |

---

## Permutation Matrix by Deal Type

| Project type | Fixture / source | Cash-flow coverage | Waterfall coverage | Investor/report coverage | Special edge guarded |
| --- | --- | --- | --- | --- | --- |
| `acquisition_minor_reno` | `tests/fixtures/tower_acquisition.json` | ✅ | ✅ | ✅ | 48-month parity window, minor-reno phase, 22 itemized expense lines |
| `acquisition_conversion` | `tests/fixtures/ap_conversion.json` | ✅ | ✅ | ✅ | hold + pre-construction + conversion path, 48-month parity window |
| `new_construction` | `tests/fixtures/synthetic_new_construction.json` | ✅ | ✅ | ✅ | milestone-driven schedule, lease-up ramp, synthetic negative-levered-IRR control case |

**Parity note:** the Tower and A&P fixtures are the current Excel-style parity baselines. The synthetic new-construction fixture is a deterministic control benchmark rather than a workbook parity source.

---

## Edge-Case Checklist

| Edge / regression risk | Covered by |
| --- | --- |
| milestone dates overriding integer month inputs | `tests/engines/test_cashflow.py` |
| fallback when only some milestone dates are present | `tests/engines/test_cashflow.py` |
| itemized operating expense lines entering period math | `tests/engines/test_cashflow.py`, `tests/scripts/test_tower_ap_parity.py` |
| debt service back-filled from waterfall results | benchmark fixture regression + waterfall engine tests |
| LP hurdle not unlocking promote split too early | `tests/engines/test_waterfall.py` |
| investor timeline cumulative totals staying consistent | `tests/api/test_routers.py` waterfall report test |
| schema-valid deal export → validate → import round trip | `tests/exporters/test_benchmark_fixtures.py` and related import/export coverage |
| scenario invalid input failing fast instead of queuing bad runs | scenario router tests |

---

## Current Tolerances

These thresholds should be treated as the automated drift guardrails for core financial regressions:

| Category | Threshold |
| --- | ---: |
| Dollar-valued fields | `±$1.00` |
| Rates / ratios / multiples | `±0.01` |
| Cash-flow parity window | first `48` monthly periods |
| Tower / A&P import validation tolerance | `0.1%` with `0.01` absolute floor |

See also: `docs/verification/baseline-2026-04-03.md` and `tests/fixtures/README.md`.

---

## Recommended Verification Commands

```bash
python -m pytest tests/engines/test_cashflow.py tests/engines/test_waterfall.py -q
python -m pytest tests/exporters/test_benchmark_fixtures.py tests/scripts/test_tower_ap_parity.py -q
python -m pytest tests/api/test_routers.py -k "waterfall_report or scenario or project_summary or portfolio_gantt" -q
python -m pytest tests/ -v
```

Use the focused commands during active development, then run the full suite before moving a work item to **Internal Review**.

---

## Manual Backtesting Checkpoints

Even when this matrix is green, a reviewer should still spot-check the core math by hand before release progression.

| Formula / behavior | Reviewer spot-check |
| --- | --- |
| Growth factor | `_growth_factor(3.0, 12)` should equal `(1.03)^1 = 1.03` |
| DSCR annualization | monthly debt service `[100, 110, 120]` → annualized median `110 × 12 = 1320`; with NOI `1980`, DSCR should be `1.50` |
| Calendar month count | `_calendar_month_count(date(2026, 1, 31), date(2026, 3, 1))` should resolve to `2` |
| Waterfall promote unlock | residual / promote splits should not activate before the LP hurdle or debt tiers are satisfied |

Use these checkpoints as the minimum manual validation prompts when a change touches projection math, waterfall sequencing, or investor-facing KPIs.

---

## Release Use

Before promoting a release that changes financial math, confirm all of the following:

- the relevant rows in this matrix have passing automated coverage,
- the benchmark/parity tests remain green,
- no tolerance thresholds were exceeded, and
- manual backtesting notes are recorded in the Plane work item before release progression.
