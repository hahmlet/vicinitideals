# Deprecate `active_phase_end` — derive loan end from Exit Vehicle

## Context

Today every Capital Module has a user-editable `active_phase_end` (e.g. "construction", "stabilized"). It's redundant and error-prone — a debt only has three real endings:

1. **Matures** (hits its amort term)
2. **Refinanced by another source** (Exit Vehicle = that source)
3. **Paid off at sale** (Exit Vehicle = sale)

Letting the user set `active_phase_end` separately from the Exit Vehicle invites timing mismatches: the retirer's `active_phase_start` might be at rank 3 but the retired's `active_phase_end` at rank 5 (phantom gap), or vice-versa. We just spent three rounds untangling these semantics — time to remove the duplicate input.

Parallel issue on the Draw Schedule: `DrawSource.active_to_milestone` is user-editable today. But a loan's draws necessarily stop when the loan is retired — so the draw window's end should also derive from Exit Vehicle. If a bridge is refi'd on 06/15, the last draw happens on or before 06/15 (possibly truncated) and the retirer begins its own cadence.

Non-loan sources (grants, equity, tax credits, owner investment) don't have an Exit Vehicle concept at all — grants are single-day forgiven infusions, equity is a one-time cash contribution held through the waterfall exit. Their UI should hide Exit Vehicle and their draw schedule should collapse to a single draw at `active_from`.

User approved breaking existing deals. Cleanup: delete all Opportunity + Deal rows at end of work so we can drop the deprecated columns without backfill.

## Design

### Funder-type classification

New set in [app/engines/cashflow.py](../app/engines/cashflow.py) near the existing `_DEBT_FUNDER_TYPES` (line ~870):

```
_EXIT_VEHICLE_APPLIES = {
  "permanent_debt", "senior_debt", "mezzanine_debt", "bridge",
  "construction_loan", "acquisition_loan", "pre_development_loan",
  "soft_loan", "bond", "owner_loan",
}
```

`owner_loan` is promoted to full debt treatment: it accrues interest, gets a debt-service line, and uses Exit Vehicle like any other loan. That means we also add `"owner_loan"` to `_DEBT_FUNDER_TYPES` in [cashflow.py](../app/engines/cashflow.py) (line ~870) and to `DEBT_FUNDER_TYPES` in [waterfall.py](../app/engines/waterfall.py) (line ~49), and remove it from any equity-classifier lists (it was loosely equity-adjacent before).

Other funder types (preferred_equity, common_equity, owner_investment, grant, tax_credit, other) remain **non-exit-vehicle sources** — single-draw, no maturity, distributed via waterfall at exit.

### Deriving the end rank

New helper `_resolve_active_end_rank(module, all_modules) -> int`:

1. If `funder_type ∉ _EXIT_VEHICLE_APPLIES` → return 99 (perpetuity; waterfall handles at exit).
2. Read `exit_terms.vehicle`:
   - `"maturity"` or absent → return 99 (engine treats as active through divestment; balloon math uses amort_term).
   - `"sale"` → return 6 (exit/divestment phase rank).
   - `<uuid>` → look up that module in `all_modules`; return its `start_rank` (from `_APS_TO_RANK`).
3. Fallback: if vehicle is unset, try the stored `active_phase_end` (legacy read; goes away after cleanup).

### Engine changes — [app/engines/cashflow.py](../app/engines/cashflow.py)

- **`_loan_pre_op_months`** (line 1061–1080): take `all_modules` as arg; replace `end_rank = _APS_TO_RANK.get(active_phase_end, 99)` with `end_rank = _resolve_active_end_rank(module, all_modules)`.
- **`_eligible_retirers` default-selection path**: use the new helper for end-rank.
- **Generic pairing pre-pass** (line ~1277): `_candidate`'s end is now derived; retirer lookup stays UUID-based (overlap not required — we already relaxed this).
- **Refi event emission** (line ~155): unchanged — still keys off `construction_retirement` written on the retirer.

### Engine changes — [app/engines/waterfall.py](../app/engines/waterfall.py)

- **`_module_active_for_phase`** (line ~1052): replace `end = module.active_phase_end; end_index = PHASE_ORDER.get(end, ...)` with the derived end-rank via the same helper (import from cashflow or duplicate the classification).

### Draw schedule — [app/engines/draw_schedule.py](../app/engines/draw_schedule.py)

- **`_settle`** (line ~314): currently `end_date = _month_start(to_milestone.date + source.active_to_offset_days)`. Change to derive `to_milestone` from the linked CapitalModule's Exit Vehicle:
  - For debt modules: resolve via vehicle → find the milestone representing the handoff (retirer's `active_from` milestone, or divestment for sale/maturity).
  - For non-debt modules (grants, equity, etc.): force single-draw — `end_date = start_date` so the while-loop emits exactly one draw event.
- Ignore `DrawSource.active_to_milestone` in the engine (column stays but unused; dropped later).

### UI — [app/templates/partials/model_builder_line_form.html](../app/templates/partials/model_builder_line_form.html)

- **Remove the "Active To" dropdown** for capital modules (currently lines ~1140–1160 in the draw-schedule section — but `active_phase_end` is also written via a hidden/visible field depending on flow — find and remove).
- **Conditionally show Exit Vehicle**: only render the `<select name="exit_vehicle">` block when the selected funder_type is in the debt set. For non-debt: hidden input with `value="maturity"` so the POST handler still sees a valid value.
- **For non-debt**: also hide draw-cadence fields; show only "Funding Date" (= `active_from`).

### Form POST — [app/api/routers/ui.py](../app/api/routers/ui.py)

- Line ~4590–4650 (capital-modules POST handler): on save:
  - Compute `active_phase_end` server-side from `exit_vehicle` and write it to the DB (keeps legacy code paths working until migration lands).
  - For non-debt funder types: set `exit_terms.vehicle = "maturity"` as a no-op sentinel; set `active_phase_end = "exit"`.
- DrawSource writeback: derive `active_to_milestone` from vehicle analogously; no user-provided value.

### Form GET — [app/api/routers/ui.py](../app/api/routers/ui.py)

- Line-form GET (~line 7603): add `show_exit_vehicle: bool` and `show_active_window: bool` to the template context, driven by funder_type. The existing `exit_vehicle_options` already lists all siblings unconditionally — no change.

### Cleanup (end of work)

After all code changes deploy green and the UI is verified on a freshly-seeded deal, wipe historical state via the Proxmox MCP against Postgres.

**Before running any DELETE**: validate the FK dependency order by running

```sql
SELECT conrelid::regclass AS table_name,
       confrelid::regclass AS references,
       conname,
       confdeltype
FROM pg_constraint
WHERE contype = 'f'
  AND (confrelid::regclass::text IN (
    'opportunities','deals','scenarios','projects','capital_modules',
    'milestones','use_lines','income_streams','operating_expense_lines',
    'unit_mixes','operational_inputs','operational_outputs',
    'waterfall_tiers','draw_sources','cash_flows','cash_flow_line_items',
    'deal_opportunities'
  ))
ORDER BY confrelid::regclass::text, conrelid::regclass::text;
```

`confdeltype = 'c'` means `ON DELETE CASCADE` — those children drop automatically when the parent is deleted, which shortens the list. Delete children before parents, reversing the dependency edges returned. Rough order (verify first!):

```
cash_flow_line_items → cash_flows → waterfall_tiers → draw_sources →
capital_modules → operational_outputs → operational_inputs → unit_mixes →
income_streams → operating_expense_lines → use_lines → milestones →
projects → deal_opportunities → deals → opportunities → scenarios
```

Then a follow-up Alembic migration (not part of this sprint) drops:
- `capital_modules.active_phase_end`
- `draw_sources.active_to_milestone`

## Files touched

| File | Change |
|---|---|
| [app/engines/cashflow.py](../app/engines/cashflow.py) | Add `_EXIT_VEHICLE_APPLIES` (incl. owner_loan), add `owner_loan` to `_DEBT_FUNDER_TYPES`, add `_resolve_active_end_rank`; update `_loan_pre_op_months`, `_eligible_retirers`, pairing pre-pass |
| [app/engines/waterfall.py](../app/engines/waterfall.py) | `_module_active_for_phase` derives end-rank; add `owner_loan` to `DEBT_FUNDER_TYPES` |
| [app/engines/draw_schedule.py](../app/engines/draw_schedule.py) | `_settle` derives `end_date` from vehicle; non-debt = single draw |
| [app/api/routers/ui.py](../app/api/routers/ui.py) | Line-form GET sends `show_exit_vehicle`; POST derives + persists `active_phase_end` and `DrawSource.active_to_milestone` from vehicle |
| [app/templates/partials/model_builder_line_form.html](../app/templates/partials/model_builder_line_form.html) | Remove Active To; gate Exit Vehicle + draw cadence on debt-type |
| [docs/FINANCIAL_MODEL.md](FINANCIAL_MODEL.md) | §2.10: document derived-end rule + funder classification |
| [docs/DATA_MODEL.md](DATA_MODEL.md) | Note deprecation of `active_phase_end` + `active_to_milestone` |

## Scope limits

- Do **not** drop the DB columns in this sprint. Keep for rollback safety; drop in a separate migration after stabilisation.
- Do **not** touch the Gantt/display reads of `active_phase_end` — the engine writes a derived value back on save, so display paths keep working unchanged.
- `owner_loan` is now treated as debt (interest accrues, debt service computed, exit vehicle applies). This is a behavior change — existing deals with `owner_loan` sources will start generating debt_service line items on next compute. Since we're wiping historical deals anyway, no migration concern.

## Verification

1. **Fresh deal walkthrough**:
   - Create opportunity → project via wizard
   - Add Acquisition Loan: form should show only Active From + Exit Vehicle (NO Active To)
   - Pick "Construction-to-Perm (auto)" as Exit Vehicle
   - Add Construction-to-Perm bond: Exit Vehicle defaults to Sale
   - Add Grant / Owner Equity: form should hide Exit Vehicle entirely
   - Compute → DB should show: acq `is_bridge=true`, bond `construction_retirement = <acq balance>`, refi line items injected at bond's active_from
2. **Engine unit tests**: `uv run pytest tests/engines/test_cashflow.py tests/engines/test_waterfall.py tests/engines/test_draw_schedule.py -q`
3. **Phase B regression**: `uv run python scripts/test_phase_b_debt.py --base-url https://viciniti.deals --auth tests/e2e/auth-state.json`
4. **Ruff**: `uv run ruff check app/`
5. **Post-deploy DB cleanup**: run the DELETE script and verify rows = 0
6. **Fresh deal smoke** after cleanup: create a new deal end-to-end, confirm everything still works
