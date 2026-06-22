# 25-Point Model Quality Checklist

**Source**: [Custom+Model+Quality+Check+List.xlsx](models/Custom+Model+Quality+Check+List.xlsx) (A.CRE-style invariant checklist, commonly circulated among institutional CRE underwriters)

**Status**: Reference document. Most items are not yet codified as automated tests. See [Coverage Map](#coverage-map) below.

---

## Why This Matters

Our current test suite asserts **point values** — given these inputs, expect this output. That catches arithmetic errors but misses a whole class of regressions where the math still balances but the *behavior* is wrong (e.g., a sign flip that still satisfies Sources = Uses, a growth-rate bug that leaves zero-growth cases correct but breaks monotonicity).

This checklist is a different paradigm: **invariants** (identity conditions that must always hold) and **monotonicity checks** (when input X moves, output Y must move in direction Z). Both are complementary to our existing tests, and together they form the kind of structural guardrails institutional investors expect on a model they're putting capital into.

It also has a second purpose: it's the same set of checks an LP's analyst would run before trusting our output. Codifying it means we can show a "model integrity" green-check panel in the UI — a trust signal that differentiates us from a black-box spreadsheet.

---

## The 25 Checks

Grouped by category for easier reasoning. Each item is phrased as an assertion that should hold true on a correctly-functioning model.

### 1. Growth Rate Invariants

1. **Untrended Return on Cost < Trended ROC** when rent growth > expense growth.
2. **↑ Rent growth → ↑ NOI, ↑ value, ↑ IRR, ↑ equity multiple** (monotonicity).
3. **↑ Expense growth → ↓ NOI, ↓ value, ↓ IRR** (monotonicity).
4. **Zero all growth rates → untrended returns = trended returns**, and NOI is flat year-over-year.

### 2. Exit & Valuation Invariants

5. **↑ Exit cap rate → ↓ value, ↓ returns** (monotonicity).
6. **Zero growth + exit cap = going-in cap → purchase price = exit value** (identity).

### 3. Sources = Uses & Capital Stack

7. **Sources = Uses** — the foundational capital-stack invariant. (Already covered — [scripts/test_phase_b_debt.py](../scripts/test_phase_b_debt.py))
8. **↑ Development costs → ↓ IRR, ↓ equity multiple** (monotonicity).
9. **↑ Interest rate on debt → ↓ levered IRR; unlevered returns unchanged** (separation test).

### 4. Revenue & Expense Sanity

10. **Revenue does not start before first units delivered** — absorption/lease-up gating.
11. **Vacancy = 100% → EGI = other income exactly** (identity — vacancy only hits rental income).
12. **OpEx = 0 → NOI = EGI exactly** (identity).
13. **NNN lease: ↑ expenses does not change NOI** — pass-through identity. *(Requires NNN pass-through logic; not currently implemented.)*

### 5. Timing & Capitalization

14. **Extending lease-up timeline → ↓ IRR** (time-value-of-money monotonicity).
15. **Negative cash flows are capitalized appropriately** — pre-stabilization shortfalls are funded by reserve/draws, not passed as equity calls.

### 6. Debt Leverage

16. **LTV = 100%, rate = 0%, no amortization → levered CF = NOI** (degenerate-case identity).
17. **Debt = 0 → Levered returns = Unlevered returns** (identity).
18. **When unlevered return > cost of debt, ↑ leverage → ↑ IRR (with ↓ DSCR)** — positive leverage monotonicity.

### 7. Waterfall & Distributions

19. **Sum of all waterfall distributions = net levered cash flows** (conservation).
20. **Sum of negative levered cash flows = total equity** (independent Sources=Uses proxy).
21. **IRR hurdles hit at the correct tier breakpoints** — promote math. (Partially covered — [test_waterfall.py:265](../tests/engines/test_waterfall.py#L265))
22. **Zero sponsor contributions + first hurdle not reached → sponsor gets zero distributions** (edge case).
23. **With catchup: GP has proportionate share prior to first promote** (catchup mechanics).
24. **Profit < 0 → GP/LP returns degrade gracefully** (no divide-by-zero, no negative promote, losses flow logically).
25. **LP returns < property-level returns** when promoted tiers exist (promote dilution).

---

## Coverage Map

### Already Covered (~8 of 25)
- **#7 Sources = Uses** — [scripts/test_phase_b_debt.py](../scripts/test_phase_b_debt.py)
- **#21 Waterfall hurdle breakpoints** — [tests/engines/test_waterfall.py:265](../tests/engines/test_waterfall.py#L265)
- **Carry formulas + DSCR parity** (supporting #9, #16) — Phase B regression
- **Self-referential draw on negative CFs** (supporting #15) — [tests/engines/test_draw_schedule.py](../tests/engines/test_draw_schedule.py)
- **Absorption / lease-up gating** (supporting #10, #14) — [tests/engines/test_cashflow_features.py](../tests/engines/test_cashflow_features.py)
- **S-curve lease-up + catchup escalation** (supporting #23) — [tests/engines/test_cashflow_features.py](../tests/engines/test_cashflow_features.py)

### Gaps Worth Filling (~16 of 25)
Mostly monotonicity and zero-out invariants — low-effort to add, high-leverage for catching regressions:
- Zero-growth identities (#4, #6)
- Zero-OpEx, 100%-vacancy identities (#11, #12)
- Monotonicity sweeps: rent growth, expense growth, exit cap, dev costs, interest rate, leverage, lease-up duration (#2, #3, #5, #8, #9, #14, #18)
- Debt-zeroed parity and degenerate LTV identity (#16, #17)
- Waterfall conservation + edge cases (#19, #20, #22, #24, #25)

### Not Yet Possible (1 of 25)
- **#13 NNN pass-through** — OpEx model does not currently distinguish NNN from gross leases. This is a real feature gap, not just a missing test.

---

## Implementation Plan (When We Pick This Up)

**Phase 1 — Test file** (~1 day): Add `tests/engines/test_model_invariants.py`. Seed one baseline scenario per deal archetype (value-add multifamily, ground-up development, stabilized acquisition). Parameterize perturbations, assert direction-of-change or identity. Skip #13.

**Phase 2 — Engine API surface** (~half day): Expose a `run_quality_checks(scenario_id) → list[CheckResult]` function in `app/engines/` that runs the same assertions against a live scenario and returns pass/fail + diagnostic details.

**Phase 3 — UI integration**: Add a "Model Integrity" panel to the scenario results page showing the 25 checks as a green/red grid. Clicking a failed check expands to show the assertion, the actual values, and a link to the relevant input. This becomes a visible trust signal for LP-facing exports.

**Phase 4 — NNN pass-through**: Scope #13 as its own feature — add `lease_type` enum to income streams, wire expense pass-through into the NOI calculation, then add the test.

---

## References

- **Source xlsx**: [docs/models/Custom+Model+Quality+Check+List.xlsx](models/Custom+Model+Quality+Check+List.xlsx)
- **Current engine math reference**: [FINANCIAL_MODEL.md](FINANCIAL_MODEL.md)
- **Testing philosophy**: [testing-strategy.md](testing-strategy.md)
