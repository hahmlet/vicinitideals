# CI E2E Test-Health Audit — 2026-06-13

**Trigger:** The automated test gate ("full gate" — the browser/E2E suite) has been
**red on `main` for ~6 days**, across every commit since the Jun-10 financial-engine
fix storm. This audit was requested while merging the LoopNet decommission (PR #13,
which itself added **zero** new failures) to find out whether the live app is genuinely
broken or the tests have drifted out of date.

**Method:** Code-based triage only — read each failing test, read the code it exercises,
and check git history since the last green run (2026-06-08). Tests were **not** re-run in
a browser. Verdicts are inferences from code + history, not reproductions.

---

## Bottom line (plain English)

**The financial screens are not broken for users.** 13 of the 16 failing tests are
**stale tests** — the app changed on purpose (a field was renamed, a section was removed
for speed, a row/column was added, a setting was locked to one option), and the tests
were never updated to match. The tests are failing because they're looking for the old
version of the screen.

- **The scariest-looking failure was a false alarm.** One test reported a cash balance
  "off by 14×" with a note that the reserve "may not have targeted correctly." That is
  **not** a real money bug — the engine is correct. The test was reading the **wrong
  column** of the cash-flow table after two new columns (DDF) were added in early June.

- **One failure is a genuine open question** (not a user-facing bug): when a deal is
  insolvent, the engine balances Sources = Uses over **2–3 recalculations**, not on the
  first click. One test clicks "compute" once and checks immediately, so it sees a
  temporary gap. Decision needed: should one click always balance, or is multi-pass
  convergence acceptable? (Details in #3 below.)

- **Two failures are unconfirmed** and need a single isolated run to localize; neither is
  attributable to the June engine changes. One of them looks like a **bug in the test
  itself** (it types a 3-decimal interest rate into a field that only accepts 2 decimals).

- **One failure is a parcel test** that will be **deleted** as part of the decommission
  (DC-3/4), so it needs no fix.

**Net:** no emergency. The product is fine; the test suite needs a catch-up pass. Until
that pass lands, the "full gate" will stay red and PRs need admin-override to merge
(as DC-1 did).

---

## Per-test findings

Legend: **STALE** = test out of date, app is fine · **REAL/DECISION** = genuine behavior
question · **UNSURE** = needs an isolated run · **DECOMMISSION** = test will be removed.

| # | Test | Verdict | Cause (commit) | Fix direction |
|---|------|---------|----------------|---------------|
| A1 | `test_dev_fee.py::test_basis_toggle_persists` | STALE | Dev-fee "basis" radio buttons replaced with a fixed hidden input — feature intentionally locked to TPC-excl-self (`a5e073b`, Jun 2) | Delete the toggle test or assert the hidden value without waiting for visibility |
| A2–A7 | `test_grant_eligibility_flow.py` (6 tests: check/uncheck-all, clearing reverts, checkbox flips label, save persists max, under-utilized yellow, wizard flips to max) | STALE | Helper `_add_grant()` waits for `#line-item-drawer`, but the **sources** wizard has always rendered into `#source-wizard-body`. Wrong selector since the tests were written (May 20). App works. | Point `_add_grant()` + assertions at `#source-wizard-body` |
| B1 | `test_gap_adjustment_slider.py::test_slider_drawer_renders_and_persists_phantom_rows` | STALE | API field renamed `revenue_delta_monthly` → `revenue_delta_annual` (`c304450`, May 29); test never updated | Replace `revenue_delta_monthly` → `revenue_delta_annual` in request + assertions |
| B2 | `test_gap_adjustment_slider.py::test_slider_perimeter_blocks_direct_phantom_mutation` | STALE | Same rename — stale request field is dropped by validation, so no phantom row is created | Same fix as B1 |
| C1 | `test_deal_lifecycle.py::test_capital_balance_transition_at_stabilization` | STALE (**false alarm**) | Two "DDF" columns added to cash-flow table (`d178e14`, Jun 3); helper `read_cashflow_table` still reads pre-DDF column indices (`cells[10/11]`, should be `cells[12/13]`). Engine reserve/gap-fill math is correct. | Update `tests/e2e/helpers.py` to read by **header name**, not fixed column position |
| C2 | `test_underwriting_flow.py::test_underwriting_view_renders_all_sections` | STALE | "Waterfall Distribution (joined)" section deliberately removed (`6468e03`, Jun 9 — a 187k-row table was locking the browser) | Drop that section title from the expected list |
| C3 | `test_phase_b_debt.py::test_phase_b_debt` | **DECISION** | CFSR auto-sizing converges Sources=Uses over 2–3 passes (`ec93115`/`e31c1bc`, Jun 10); test computes once → temporary Sources≠Uses gap on insolvent cases | Decide invariant: either test computes 2–3× before checking, **or** engine re-sizes the bond in the same pass it adds the CFSR use line |
| C4 | `test_ui_features_april_2026.py::test_calc_status_modal_shows_three_factors` | STALE | 4th "Account Balance" row added to the calc-status modal (`bcf9fb7`, Jun 1); test asserts exactly 3 | Change assertion `== 3` → `== 4`; add "Account Balance" check |
| C5 | `test_unified_wizard_flow.py::test_unified_wizard_data_reaches_deal_via_api` | UNSURE | Data-write paths look intact; long multi-stage happy path. No in-window commit obviously breaks it | Run isolated with `-s` to localize the failing step (suspect wizard-step nav/timeout) |
| C6 | `test_source_wizard_debt_rate.py::test_debt_wizard_accepts_fractional_rate` | UNSURE / likely STALE | Test types `6.875` (3 decimals) but the input is `step="0.01"` (2 decimals) → HTML5 step-validation rejects it. Test/field mismatch, not the engine storm | Use a 2-decimal rate (e.g. `6.88`) **or** bump input `step` to allow 3 decimals if needed |
| D | `test_opportunity_wizard.py::test_attach_parcel_advances_to_review` | DECOMMISSION | Parcel attach flow — being removed in parcel decommission DC-3/4 | Delete with the parcel UI; no fix |

---

## Recommended cleanup order (when the test catch-up is scheduled)

1. **Trivial stale-test edits** (A1, A2–A7, B1, B2, C2, C4) — pure test/selector/field
   updates, no app change. Clears 11 of 16.
2. **C1 helper fix** — make `read_cashflow_table` select columns by header name so future
   column inserts stop silently breaking it. Clears the false-alarm.
3. **C5, C6** — run each in isolation (`uv run pytest <file>::<test> -v -s`) to confirm;
   C6 is probably a one-line test value change.
4. **C3 phase_b** — the one product decision (single-compute parity vs. multi-pass
   convergence). Resolve the invariant, then fix test or engine accordingly.
5. **D** — drops out automatically when the parcel UI is decommissioned.

After 1–3, only C3 (a decision) and possibly C5 would remain — at which point the full
gate can go green again and merges stop needing admin-override.

---

*Audit performed code-only (no browser runs). If any verdict needs hard confirmation,
reproduce with `$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest <file>::<test> -v -s`.*
