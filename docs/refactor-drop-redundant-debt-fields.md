# Refactor — Drop Redundant Debt Fields, Source Hold from Debt Modules

**Origin decisions:**
- S313 (mem:4157, 2026-04-29): Hold Period field removed from Deal Settings. Source from Operation Stabilized.
- 2026-04-29 addendum: per-loan `hold_term_years` becomes required field on every **permanent-debt** CapitalModule. Deal horizon = exit milestone if present, else MAX(perm-debt hold_term), else stabilized milestone length.

**Scope:** permanent debt only. Construction loans, bond, mezzanine, equity — out of scope. Equity hold/exit timing is a separate punch-list item.

## Decision summary

| Item | Before | After |
|---|---|---|
| Hold period source | `OperationalInputs.hold_period_years` (deal-level scalar) | Per-perm-loan `CapitalModule.source.hold_term_years` + Milestone(phase=exit) override |
| Perm rate | `OperationalInputs.debt_terms.permanent_debt.rate_pct` | `CapitalModule.source.interest_rate_pct` only |
| Perm amort | `OperationalInputs.debt_terms.permanent_debt.amort_years` | `CapitalModule.carry.amort_term_years` only |
| DSCR minimum | `OperationalInputs.dscr_minimum` (deal-level) | `CapitalModule.source.dscr_min` (per-loan) |
| Loan balloon timing | Forced to end of stabilized phase regardless of vehicle | min(hold_term, exit_milestone_offset) |

## Horizon resolution

```
1. exit_milestone exists       → horizon = exit_milestone.computed_start
2. else has perm debt          → horizon = MAX(perm_debt.hold_term_years) × 12
3. else                        → horizon = stabilized milestone length (months)
4. no stabilized milestone     → engine error, deal invalid
```

Step 3 fires Cover-sheet banner: "No exit milestone, no perm debt; modeled horizon = stabilized phase length (X months)." User sees fallback, can add exit if wrong.

Per-loan amort runs independently. Loan balloons at `min(hold_term × 12, horizon)`. Hold_term > amort_term → loan fully amortizes mid-hold. Hold_term < amort_term → residual balloon at hold_term end.

## Fields to drop

**`OperationalInputs`:**
- `hold_period_years`
- `perm_rate_pct`
- `perm_amort_years`
- `debt_terms` (JSON)
- `dscr_minimum`

`hold_phase_enabled` + `hold_months` retained — they control insertion of a separate "hold" phase between acquisition and renovation (value-add operate-then-renovate pattern), unrelated to perm-debt hold period despite name similarity. No UI surface today; API/JSON-import only. Out of perm-debt-only scope.

**Model Settings UI panel:** Hold Period, Perm Rate, Amort, DSCR Minimum (header was already pre-fill placeholder, not authoritative).

**Deal Setup Wizard:** same fields, plus add per-debt-source `hold_term_years` capture.

## Fields to add

**`CapitalModule.source` (new keys):**
- `hold_term_years` — required when `funder_type == permanent_debt`. Other funder types unaffected.
- `dscr_min` — optional, used when sizing via DSCR constraint (perm-debt only)

## Phases

### Phase A — engine + tests
0. `grep -r hold_phase_enabled app/ tests/` — confirm only engine references. If template/route refs surface, schedule for Phase C.
1. `cashflow.py:_build_phases` — replace stabilized.months calc with horizon resolver above.
2. `cashflow.py::_build_debt_service_stream` (or equivalent) — per-loan balloon at `min(hold_term × 12, horizon)`.
3. `engines/sensitivity_matrix.py` — replace `inputs.hold_period_years` reads with horizon helper.
4. `engines/underwriting.py` — same scan + replace.
5. Tests:
   - `tests/engines/test_cashflow.py` — 6 cases:
     * exit milestone at 60mo → horizon=60mo
     * no exit + single 25Y perm debt → horizon=300mo, loan amortizes full
     * no exit + multi-perm-debt (10Y senior + 25Y mezz) → horizon=300mo (MAX), senior balloons at 120mo
     * no exit + all-cash, stabilized=72mo → horizon=72mo, banner fires
     * hold_term < amort_term → balloon residual at hold_term end
     * refi vehicle + exit milestone before refi date → loan refis at exit, not refi date
   - `scripts/test_phase_b_debt.py` — replace `hold_period_years` assertions with `hold_term_years` per-loan.

### Phase B — schema + write paths
**Sequencing:** Phase D migration runs first (backfills `hold_term_years` on every existing perm-debt module), then Phase B Pydantic enforcement deploys. Avoids legacy modules failing validation.

1. `schemas/capital.py::CapitalSourceSchema` — add `hold_term_years`. Pydantic validator: required when `funder_type == permanent_debt`.
2. `cashflow.py::_auto_size_debt_modules` — drop reads of `inputs.debt_terms`, `inputs.perm_rate_pct`, `inputs.perm_amort_years`. Source from CapitalModule only.
3. `cashflow.py::_dscr_capped_size` — drop `inputs.dscr_minimum` read. Use `module.source.dscr_min`. Fallback to 1.20 if unset.
4. `api/routers/ui.py` lines ~7080-7160 (form save) — drop reads of removed fields.
5. `api/routers/ui.py:7614` `deal_setup_wizard_complete` — write `hold_term_years` to each created perm-debt CapitalModule. Default to value captured in wizard step.
6. `templates/partials/model_builder_line_form.html` — add `hold_term_years` input, perm-debt rows only. Required client + server side. Display alongside Amort.

### Phase C — UI cleanup
1. `templates/model_builder.html` — strip Hold Period, Perm Rate, Amort, DSCR Minimum from Model Settings drawer.
2. `templates/partials/deal_setup_wizard.html` — drop scenario-level hold/perm/amort step. Add per-debt-source hold_term capture in debt-config step.
3. `templates/partials/model_builder_panel.html` — strip stale references.

### Phase D — migration + cleanup (runs BEFORE Phase B Pydantic enforcement)
1. **Alembic revision** — backfill + drop:
   ```
   For each CapitalModule cm where funder_type == 'permanent_debt':
     cm.source['hold_term_years'] = cm.carry.amort_term_years or 5
   For each CapitalModule cm where funder_type == 'permanent_debt'
                                AND OperationalInputs.dscr_minimum is set:
     cm.source['dscr_min'] = OperationalInputs.dscr_minimum
   Drop columns: hold_period_years, hold_phase_enabled, hold_months,
                 perm_rate_pct, perm_amort_years, debt_terms, dscr_minimum
   ```
2. `exporters/json_export.py` — stop writing legacy keys.
3. `exporters/json_import.py` — read legacy keys with deprecation warning. **Hard cutoff: 2026-06-01.** After that, drop reader.
4. `exporters/investor_export.py` — Cover sheet: drop "Hold Period" if listed as a stored KPI; show per-loan `hold_term_years` in Debt Schedule; render fallback banner ("No exit milestone, no perm debt; modeled horizon = stabilized phase length (X months)") when horizon resolver step 3 fires.
5. `exporters/excel_export.py` — same as investor_export for Hold Period + Debt Schedule.

### Phase E — verification
1. Full pytest run: `uv run pytest tests/ -q --ignore=tests/e2e` — green before merge.
2. Phase B regression suite (`scripts/test_phase_b_debt.py --base-url ...`) — all 8 tests pass.
3. Re-export Subject Model V6 from canonical scenario `https://viciniti.deals/models/7dcc6f09-36b0-4ef5-9e3a-ad373542a9c6/`:
   - "Total Modeled Duration (months)" reflects exit OR MAX hold_term, not buggy 62
   - Debt Schedule shows per-loan `hold_term_years` column
   - Maturity vehicle + no exit → loan amortizes through full hold_term
   - Sale vehicle + exit → balloon at exit
   - Refi vehicle + exit before refi → loan refis at exit, not refi date
4. Browser smoke:
   - Model Settings panel: no Hold/Perm/Amort/DSCR fields
   - Wizard: captures hold_term_years per perm-debt source
   - Edit Source (perm-debt): hold_term_years field visible + editable
5. Worktree cleanup after merge + deploy verified:
   ```
   git worktree remove ../vicinitideals-worktrees/drop-redundant-debt-fields
   git branch -d feature/drop-redundant-debt-fields
   ```

## Files touched (per mem:4192)

| Layer | Files |
|---|---|
| ORM | `app/models/deal.py`, `app/models/capital.py` |
| Schemas | `app/schemas/deal.py`, `app/schemas/capital.py`, `app/schemas/underwriting_tools.py` |
| Engines | `app/engines/cashflow.py`, `app/engines/waterfall.py`, `app/engines/underwriting.py`, `app/engines/sensitivity_matrix.py` |
| Templates | `app/templates/model_builder.html`, `partials/model_builder_panel.html`, `partials/model_builder_line_form.html`, `partials/deal_setup_wizard.html` |
| Exporters | `app/exporters/investor_export.py`, `excel_export.py`, `json_export.py`, `json_import.py`, `deal_export.py` |
| Routes/Tasks | `app/api/routers/ui.py`, `app/tasks/scenario.py` |
| Migration | new Alembic revision under `alembic/versions/` |
| Tests | `tests/engines/test_cashflow.py`, `scripts/test_phase_b_debt.py` |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Existing perm-debt modules lack `hold_term_years` post-deploy | Phase D backfill: `hold_term_years = amort_term_years or 5` |
| Existing deals' hold-period intent lost | User-confirmed acceptable; existing deals are throwaway/test |
| Sensitivity engine silently breaks | Phase A bundles sensitivity update with cashflow change |
| Legacy JSON imports break | 2026-06-01 hard cutoff for compat reads |
| Per-loan DSCR sizing path regresses | Phase B includes `_dscr_capped_size` test in Phase B regression suite |
| Fallback horizon (stabilized length) fires silently | Cover-sheet banner when resolver step 3 hits |
| Phase B Pydantic validator rejects legacy modules | Phase D runs first; backfill ensures no NULL `hold_term_years` |

## Worktree

```
git worktree add ../vicinitideals-worktrees/drop-redundant-debt-fields \
                 -b feature/drop-redundant-debt-fields main
cp .env ../vicinitideals-worktrees/drop-redundant-debt-fields/.env
cd ../vicinitideals-worktrees/drop-redundant-debt-fields && uv sync
```

## Out of scope

- `expense_growth_rate_pct_annual` (not a debt field; stays on OpInputs)
- Construction loan, bond, mezzanine hold semantics (perm debt only this pass)
- Equity hold/exit timing (separate punch-list item)
- Waterfall tier configuration UI (separate punch list item, V2-E)
- Per-year returns matrix enhancement (already shipped V4 H1)
- Color convention nits (cosmetic, not refactor scope)
