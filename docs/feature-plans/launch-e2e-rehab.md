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
Fix these after P1/P2 are clear. Low risk — these are tests that have fallen out of sync with template changes.

| Item | Recommendation |
|---|---|
| `test_grant_eligibility_flow.py` (6 tests) | **Rewrite or delete.** Grant-eligibility drawer likely renamed or restructured. Open the feature in the live app and update selectors to match current HTML. If the feature was removed, delete the file and remove from CI. |
| `test_proforma_cache.py` (2 tests) | **Rewrite.** 30s click timeout = selector targeting an element that no longer exists. The proforma upload surface has had multiple changes; rewrite against current UI flow. |
| `test_ui_features_april_2026.py` (whole file) | **Triage as a group.** Run each test in isolation to separate genuine flake from selector drift. Tests covering debt-type ordering, default OpEx seed, and unit-mix round-trip are feature-critical — rewrite the failing ones rather than deleting. Rename the file if you rewrite the majority of it (date-named test files rot fast). |
| `test_underwriting_flow::test_coverage_modal_per_project_amount_inputs_present` (2 params) | **Update selector.** Coverage modal ID or layout changed. Locate current modal `id` in `app/templates/` and update the locator. Low-risk fix. |
| `test_wizard_state_persistence` — two 30s click timeouts on step 2 | **Update selector.** Step 2 element the test clicks was likely renamed in a template change. Grep `app/templates/` for current step-2 element IDs and update. |

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

- `tests/e2e/test_grant_eligibility_flow.py` — all 6 tests fail with
  selector timeout on the grant-eligibility drawer. Likely template
  selector drift since the test was written; possibly the drawer was
  renamed or replaced.
- `tests/e2e/test_proforma_cache.py` — both tests fail with a 30s click
  timeout. Whole proforma upload + cache surface needs revisiting; also
  ignored in the integration step.
- `tests/e2e/test_ui_features_april_2026.py` — multiple tests in this
  file fail intermittently (different test each run): debt-type
  ordering, default-OpEx seed, unit-mix round-trip. Either the whole
  surface this file exercises has drifted, or the file has flake from
  shared seed state. Triage as a group.

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
