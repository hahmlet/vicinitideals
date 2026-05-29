# Launch-prep E2E rehab follow-up

## Triage recommendations (added 2026-05-28)

### Priority 1 — Fix first (real engine math bugs)
These are correctness regressions in the financial model, not test maintenance. Broken numbers = broken product.

| Item | Recommendation |
|---|---|
| ~~`test_phase_b_debt` — 3 failing variants (`ir_12mo`, `ci_12mo`, `ir_3mo_short`)~~ | **Fixed 2026-05-28.** Test fixtures omitted `ltv_pct=100`; `_funded=75%*base_costs` caused the balance invariant to fail. Fixed in commit `75afc66`. |
| ~~`test_cashflow_hypothesis.py`~~ | **Fixed 2026-05-28.** `_compute_period` produced negative EGI when `bad_debt+concessions > after_vacancy`. Fix: proportionally cap both deductions so EGI floors at zero while preserving accounting identity. Fixed in commit `75afc66`. |

### Priority 2 — Likely real product bugs (verify before dismissing as drift)

| Item | Recommendation |
|---|---|
| ~~`test_unified_wizard_flow::test_unified_wizard_data_reaches_deal_via_api` — Approve button disabled~~ | **Closed 2026-05-28.** Test passes as-is — no product bug found. |
| ~~`test_wizard_state_persistence::test_successful_step_submit_clears_localstorage_key` — key is None~~ | **Fixed 2026-05-28.** `revenue_opex` is the default radio; clicking it fires no `change` event so localStorage was never written. Changed test click to `noi` to trigger the save handler. |
| ~~`test_opportunity_wizard::test_attach_parcel_advances_to_review` — parcel search returns no result~~ | **Closed 2026-05-28.** Test passes as-is — seed data present, search backend healthy. |

### Priority 3 — Test maintenance (selector/template drift, no evidence of product regression)
**All P3 items closed 2026-05-29 (commits `c304450`, `e84c7c5`).** Selector fixes shipped to main; per-test deselects lifted in CI (see table below).

| Item | Recommendation |
|---|---|
| ~~`test_grant_eligibility_flow.py` (6 tests)~~ | **Fixed 2026-05-29 (`c304450`).** `_add_use` helper updated to use `#uses-wizard-body` + `#uw-next`. |
| ~~`test_proforma_cache.py` (2 tests)~~ | **Fixed 2026-05-29 (`c304450`).** `_reach_upload_step` + `_upload` selectors updated to `#proforma-file` + `#step1-submit`. CI ignore still in place pending green-run confirmation. |
| ~~`test_ui_features_april_2026.py` (whole file)~~ | **Fixed 2026-05-29 (`c304450`).** Added `pre_development` milestone type; updated opex labels to 20-item list. |
| ~~`test_underwriting_flow::test_coverage_modal_per_project_amount_inputs_present` (2 params)~~ | **Fixed 2026-05-29 (`c304450`).** Coverage modal inputs are `type=text` after JS formatter runs; selector matches `name^='amount['` instead. |
| ~~`test_wizard_state_persistence` — two 30s click timeouts on step 2~~ | **Fixed 2026-05-29 (`c304450`).** Switched to stable `#step1-submit` id; `expect().to_be_checked()` for async restore. |

### Sequencing
Fix P1 engine bugs first — they affect export accuracy and are user-visible. P2 items can be verified in the live app in 10 minutes each before spending time on test code. P3 is pure maintenance and can be batched into one sitting.

Pre-existing E2E failures deselected on 2026-05-28 during the
`fix/ci-gates-sweep` launch-prep CI sweep so the gate could land green.
Each entry must be triaged: real product bug → file ticket and fix;
stale test → rewrite or delete. Remove the entry from the E2E step in
`.github/workflows/ci.yml` once the test is green again.

## Unit / integration files ignored

- ~~`tests/engines/test_cashflow_hypothesis.py`~~ — Closed 2026-05-28.
  10-invariant version from `feature/layer-d-hypothesis` adopted
  (commit `5d97548`); underlying EGI-floor engine bug fixed in
  `75afc66`; CI deselects lifted in `cb2463b`. Layer D (Hypothesis
  property-based engine testing) of the launch monetization plan is
  closed.

## Whole E2E files ignored

- ~~`tests/e2e/test_grant_eligibility_flow.py`~~ — **Closed 2026-05-29
  (`c304450`).** Helper selector fixes; whole-file ignore lifted in CI.
- `tests/e2e/test_proforma_cache.py` — selectors fixed in `c304450`
  (`#proforma-file`, `#step1-submit`), but CI ignore still in place at
  `.github/workflows/ci.yml:219` pending a confirmed green run. Lift
  the ignore once verified.
- ~~`tests/e2e/test_ui_features_april_2026.py`~~ — **Closed 2026-05-29
  (`c304450`).** `pre_development` milestone + 20-item opex labels;
  whole-file ignore lifted in CI.

## Per-test deselects

| Test | Failure |
|---|---|
| ~~`test_opportunity_wizard.py::test_attach_parcel_advances_to_review`~~ | **Closed 2026-05-28.** Passes as-is. |
| ~~`test_ui_features_april_2026.py::*`~~ | Whole file ignored — see above. |
| ~~`test_underwriting_flow.py::test_coverage_modal_per_project_amount_inputs_present` (both params)~~ | **Fixed 2026-05-29.** JS formatter converts `type="number"` → `type="text"` after HTMX swap; selector changed to `input[name^='amount[']`. |
| ~~`test_unified_wizard_flow.py::test_unified_wizard_data_reaches_deal_via_api`~~ | **Closed 2026-05-28.** Passes as-is. |
| ~~`test_wizard_state_persistence.py::test_step2_checkbox_saves_to_localstorage`~~ | **Fixed 2026-05-29.** Step 1 submit button selector changed to `#step1-submit` (stable ID, text varies). |
| ~~`test_wizard_state_persistence.py::test_successful_step_submit_clears_localstorage_key`~~ | **Fixed 2026-05-28.** `revenue_opex` is default; test now clicks `noi` to trigger `change` event. |
| ~~`test_wizard_state_persistence.py::test_step2_restores_from_localstorage_on_swap_in`~~ | **Fixed 2026-05-29.** Same `#step1-submit` fix; assertions changed to `expect().to_be_checked()` for async restore timing. |
| ~~`test_phase_b_debt.py::test_phase_b_debt[chromium-ir_12mo]`~~ | **Fixed 2026-05-28.** Root cause: test omitted `ltv_pct=100`, so `_funded=75%*base_costs` and balance invariant failed. Set `ltv_pct=100` in test fixture; seed.py wizard helper now fills LTV in Step 5. |
| ~~`test_phase_b_debt.py::test_phase_b_debt[chromium-ci_12mo]`~~ | **Fixed 2026-05-28.** Same root cause as ir_12mo. |
| ~~`test_phase_b_debt.py::test_phase_b_debt[chromium-ir_3mo_short]`~~ | **Fixed 2026-05-28.** Same root cause as ir_12mo. |
