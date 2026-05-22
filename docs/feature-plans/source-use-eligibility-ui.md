# Feature Plan: Source-Use Eligibility UI + Capped-Consumption Grant Semantics

**Status:** Draft
**Date:** 2026-05-20
**Owner:** Steph Ketch
**Related backend:** Phase H (May 2026) — `app/engines/source_routing.py`, migration `0088_source_use_eligibility.py`

---

## 1. Problem

Backend eligibility routing (Phase H) added two whitelist columns:
- `capital_modules.eligible_use_tags` (varchar[], category whitelist)
- `use_lines.eligible_module_ids` (UUID[], per-line whitelist)

Engine in `app/engines/source_routing.py` honors them. **UI exposes neither.** Grants like "OR-MEP / Energy Trust" that should fund only Construction Uses currently fund anything.

Today's grant model: fixed `source.amount`, contributes guaranteed dollars regardless of Use needs. Real-world grant behavior: a **cap** that consumes only against eligible Uses, never exceeding actual eligible Use total.

---

## 2. Target Semantics

### Grant with no eligibility (default, unchanged)
- User enters `Amount` ($)
- Source contributes that amount, fixed
- Behaves like equity placeholder

### Grant with eligibility selected
- User input becomes `Maximum ($)` (cap)
- `Amount` field becomes computed, read-only
- Engine computes per-period: `amount = min(maximum, sum_of_eligible_use_consumption)`
- If `amount < maximum` → row highlighted yellow (under-utilized)
- Active From auto-set to earliest eligible Use start (read-only)
- Active To auto-set to last period grant consumes (or max eligible Use end)

### Consumption order across multiple eligible Uses
1. Use start period ascending
2. Use amount descending (ties broken largest first)

### Multiple grants competing for same Use
1. `stack_position` ascending (grant earlier in stack consumes first)
2. Each grant decrements per-Use "remaining eligible bucket"
3. No pro-rata split (out of scope)

### Edge cases
- Eligibility cleared → revert to plain `Amount`, clear `maximum`
- Use timing changes → grant timing recomputes on next compute (acceptable)
- Use deleted → drop ID from grant's eligibility list; if list becomes empty after deletion → revert to plain Amount
- Use amount = $0 → grant contributes $0 regardless of cap

---

## 3. Data Model Changes

### Migration `0094_source_maximum.py`
Add column to `CapitalSourceSchema` JSONB:
- `maximum: Decimal | None` — user-entered cap when eligibility set; null when permissive

Note: `capital_modules.source` is JSONB; schema lives in `app/schemas/capital.py`. No SQL DDL needed for adding a key (JSONB allows it), but bump schema version and document in `docs/DATA_MODEL.md`.

### Schema update
File: `app/schemas/capital.py` (or wherever `CapitalSourceSchema` lives)
```python
class CapitalSourceSchema(BaseModel):
    # existing fields …
    amount: Decimal | None = None       # engine-computed when eligibility set
    maximum: Decimal | None = None      # user-entered cap when eligibility set
```

### Drop `eligible_use_tags` from UI scope (engine still honors it)
Per-Use-line approach uses `use_lines.eligible_module_ids` only. Tag-based whitelist remains in DB/engine for backward compat but UI does not expose it.

---

## 4. Engine Changes

### File: `app/engines/cashflow.py`

New helper in `_auto_size_debt_modules`, called BEFORE auto-sized debt gap-fill:

```python
def _resolve_grant_caps(scenario, use_lines, capital_modules):
    """Compute grant `source.amount` from `source.maximum` + eligibility.

    Mutates module.source['amount'] for each grant with eligibility set.
    Tracks per-Use remaining eligible bucket so two grants on same Use
    cannot both claim full amount.
    """
    # Build per-Use remaining bucket
    remaining = {u.id: Decimal(u.amount or 0) for u in use_lines}

    # Iterate grants in stack_position order
    grants = [m for m in capital_modules
              if not m.source.get('auto_size')
              and m.source.get('maximum') is not None]
    grants.sort(key=lambda m: int(m.stack_position or 0))

    for g in grants:
        cap = Decimal(g.source['maximum'])
        eligible_use_ids = g.source.get('eligible_use_ids') or []
        if not eligible_use_ids:
            continue  # no eligibility → falls back to fixed amount path

        # Order eligible Uses: start period asc, amount desc
        eligible_uses = sorted(
            [u for u in use_lines if str(u.id) in eligible_use_ids],
            key=lambda u: (_use_start_period(u), -Decimal(u.amount or 0)),
        )

        consumed = Decimal(0)
        for u in eligible_uses:
            if consumed >= cap:
                break
            take = min(remaining[u.id], cap - consumed)
            remaining[u.id] -= take
            consumed += take

        g.source['amount'] = consumed
        # Active From/To computed by separate timing pass below
```

### Active From/To derivation
Run after `_resolve_grant_caps`. For each grant with eligibility:
- `active_from` = min eligible Use start period (using `_use_start_period`)
- `active_to` = period where cumulative consumption hits cap, else max eligible Use end

### Draw schedule
Grant draws follow eligible Use draw cadence proportionally. Existing draw-schedule engine handles per-period via `source.amount` total + Active window. New behavior: when cap < eligible total, grant draws taper off at cap. Implementation:
- In `app/engines/draw_schedule.py`, when grant `source.maximum` set, replace per-period draw calc with: distribute `source.amount` (already capped) across eligible Uses' periods in consumption order.

### Ordering invariant
`_resolve_grant_caps` must run:
1. AFTER Use line amounts are finalized (post-developer-fee, post-finance-cost computation)
2. BEFORE `_auto_size_debt_modules` gap-fill (so debt sees correct grant contribution)

---

## 5. UI Changes

### File: `app/templates/partials/model_builder_line_form.html`

**Edit form — Grant/Forgivable Loan/Tax Credit:**
- New section: "Eligibility (optional)"
  - Multi-select checklist of all current Uses (id + label) for this scenario
  - Helper text: "If checked, this source funds only the selected Uses up to the Maximum below."
- When ≥1 Use checked:
  - "Amount" label → "Maximum ($)"
  - Hidden field `source_maximum` becomes the active input
  - Hidden field `source_amount` shows read-only computed value
  - Active From/To inputs disabled, show computed values
- When 0 Uses checked:
  - "Maximum ($)" label → "Amount"
  - `source_amount` is the active input
  - `source_maximum` cleared/null
  - Active From/To inputs editable

**JS handler (`swTypeChanged` + new `_onEligibilityToggle`):**
```js
function _onEligibilityToggle() {
  const anyChecked = $$('input[name="eligible_use_ids"]:checked').length > 0;
  $('#amount-label').text(anyChecked ? 'Maximum ($)' : 'Amount');
  $('#source_amount_input').prop('readonly', anyChecked);
  $('#source_maximum_input').prop('hidden', !anyChecked);
  $('#active_from_input').prop('disabled', anyChecked);
  $('#active_to_input').prop('disabled', anyChecked);
}
```

### Sources & Uses table (`partials/sources_uses_table.html`):
- New CSS class `row-under-utilized` (yellow background)
- Server-side renders class when `source.amount < source.maximum` AND `source.maximum is not None`
- Tooltip: "Grant funded $X of $Y maximum — $Z unused (eligible Uses don't cover cap)"
- Maximum column added (hidden unless any source has maximum set)

### Add wizard (sw-step-1 + sw-step-3):
- Same eligibility checklist when type ∈ `_FIXED_AMOUNT` (`grant`, `forgivable_loan`, `tax_credit`)
- Step 3 (Committed Amount) label flips between "Amount" and "Maximum" based on eligibility checkboxes
- Validation in `_swCheck`: maximum required when any eligibility checked

---

## 6. API Changes

### File: `app/api/routers/ui.py`

Capital module save handler (~line 6001 area, where `source_amount` is mapped):
- Parse `eligible_use_ids[]` from form → write to each Use's `eligible_module_ids`
- Parse `source_maximum` → `source.maximum`
- When eligibility list non-empty: do NOT trust `source_amount` from form (engine computes)
- When eligibility list empty: clear `source.maximum`, accept `source_amount` as-is

Validation:
- Reject save if maximum present but no eligibility checked
- Reject save if eligibility checked but maximum absent or ≤ 0

Use-line side updates:
- For each Use ID newly in this grant's eligibility list: append grant's module ID to `use_line.eligible_module_ids`
- For each Use ID removed: remove grant's module ID from `use_line.eligible_module_ids`
- Maintain bidirectional consistency on every save

---

## 7. Test Plan

### Unit tests — engine

**File:** `tests/engines/test_grant_cap_resolution.py` (new)

| Test | Setup | Assertion |
|---|---|---|
| `test_grant_no_eligibility_uses_amount_directly` | Grant amount=$200k, no eligibility | `source.amount` unchanged, `maximum` null |
| `test_grant_cap_under_eligible_sum` | Grant max=$250k, eligible Uses sum=$500k | `source.amount = 250000` |
| `test_grant_cap_over_eligible_sum` | Grant max=$250k, eligible Uses sum=$180k | `source.amount = 180000`, under-utilized flag |
| `test_two_grants_same_use_stack_position_wins` | Grant A pos=1 max=$250k, Grant B pos=2 max=$250k, only Use=Site Work ($200k) | A=$200k, B=$0 |
| `test_consumption_order_period_asc_amount_desc` | Site Work $200k mo 1, FF&E $300k mo 1, grant max=$250k both eligible | FF&E consumed first (larger): $250k → FF&E, $0 → Site Work |
| `test_grant_timing_follows_uses` | Site Work mo 1–2, FF&E mo 6, grant max=$250k both eligible | `active_from=1`, `active_to=6` |
| `test_grant_timing_caps_at_consumption` | Single Use mo 1, grant max > Use | `active_to` = Use end period |
| `test_use_deletion_clears_orphan_eligibility` | Delete Use; grant referenced it | Grant's eligibility list cleared if empty → revert to plain Amount |

**File:** `tests/engines/test_source_routing.py` (existing — extend)
- Add tests for two-grant tie-break by stack_position
- Add test that empty eligibility still routes permissively

### Integration tests — API

**File:** `tests/api/test_capital_grant_eligibility.py` (new)

| Test | Action | Assertion |
|---|---|---|
| `test_save_grant_with_eligibility_persists_maximum` | POST grant with `source_maximum=250000` + `eligible_use_ids=[u1, u2]` | DB has `source.maximum=250000`, Use rows have grant ID in `eligible_module_ids` |
| `test_save_grant_clears_maximum_when_eligibility_removed` | PUT remove all eligibility | `source.maximum=null`, Use rows no longer reference this grant |
| `test_save_rejects_maximum_without_eligibility` | POST `source_maximum=250000` + no eligibility | 422 validation error |
| `test_save_rejects_eligibility_without_maximum` | POST eligibility + no maximum | 422 validation error |
| `test_bidirectional_sync_on_use_eligibility_change` | PUT Use's `eligible_module_ids` directly | Grant's eligibility list reflects update on next read |
| `test_compute_returns_capped_amount` | Grant max=$250k, eligible Use=$180k → POST recompute | Response includes `source.amount=180000` |

### E2E tests — Playwright

**File:** `tests/e2e/test_grant_eligibility_flow.py` (new)

| Test | Flow | Assertion |
|---|---|---|
| `test_add_grant_with_eligibility_in_wizard` | Open Sources wizard → choose Grant → enter name → check Site Work + Hard Costs in eligibility → enter Maximum=$250k → submit | Grant appears in S&U table with Maximum column showing $250k, computed Amount column showing min(cap, eligible sum) |
| `test_edit_grant_toggle_eligibility_changes_field_label` | Open grant edit drawer → check first Use → assert "Amount" label changes to "Maximum ($)" → uncheck → assert reverts to "Amount" | Label text + field readonly state correctly toggle |
| `test_under_utilized_grant_shows_yellow_row` | Set up grant max=$250k eligible for Use of $180k → compute | S&U table row has CSS class `row-under-utilized`, tooltip text matches |
| `test_fully_utilized_grant_no_yellow` | Grant max=$200k, eligible Use=$200k | No yellow row, no under-utilized tooltip |
| `test_two_grants_competing_first_wins` | Grant A stack=1 max=$250k, Grant B stack=2 max=$250k, single Use=$200k both eligible → compute | A shows $200k, B shows $0 with under-utilized indicator |
| `test_active_from_to_readonly_when_eligibility_set` | Open grant edit, check Use → assert Active From/To inputs disabled with computed values | Fields have `disabled` attribute, values match earliest/latest eligible Use periods |
| `test_active_from_updates_when_use_timing_changes` | Set up grant eligible for Use starting month 6 → change Use start to month 1 → recompute | Grant Active From displays month 1 |
| `test_use_deletion_removes_orphan_eligibility` | Delete Use referenced by grant → reload S&U table | Grant edit form no longer shows deleted Use; if it was sole eligibility, grant reverts to plain Amount |
| `test_sources_equal_uses_with_capped_grant` | Build deal: Uses=$1M, Grant max=$250k eligible for Hard Costs ($500k) → set auto-sized debt for gap → compute | Sources = Uses (debt fills correct gap of $1M - $250k = $750k) |

### Phase B debt regression
**File:** `scripts/test_phase_b_debt.py` (extend existing)
- Add scenario: grant with eligibility, verify Sources = Uses parity
- Verify DSCR-capped flow still works when grant under-utilization shrinks effective gap

---

## 8. Documentation Updates

After implementation:
- `docs/FINANCIAL_MODEL.md` §2.11 — extend with capped-consumption semantics, two-grant tie-break, timing derivation
- `docs/DATA_MODEL.md` — document `source.maximum` JSONB key on `capital_modules.source`
- Migration `0094_source_maximum.py` — note schema-only change (JSONB add)

---

## 9. Migration Strategy

### Backfill
- No backfill needed. Existing grants have no `eligible_use_ids` set → permissive path, `source.maximum` stays null, behavior identical to today.
- First time a user checks eligibility on existing grant: migrate `source.amount` value into `source.maximum`, set `amount = null` (will be computed on next save+compute).

### Feature flag
Not needed. Backward compatible — empty eligibility = current behavior.

### Rollout
1. Migration + engine changes + tests → deploy
2. UI changes → deploy
3. Update OR-MEP / Energy Trust grant on production deal `cf0e77c3` as smoke test
4. Update docs

---

## 10. Build Sequence

| Step | Files | Why first |
|---|---|---|
| 1. Migration + schema | `alembic/versions/0094_source_maximum.py`, `app/schemas/capital.py` | Foundation |
| 2. Engine `_resolve_grant_caps` | `app/engines/cashflow.py` (new helper) | Core logic, testable in isolation |
| 3. Engine timing derivation | `app/engines/cashflow.py` (Active From/To pass) | Depends on step 2 |
| 4. Draw schedule update | `app/engines/draw_schedule.py` | Depends on step 2 |
| 5. Unit tests | `tests/engines/test_grant_cap_resolution.py` | Validates 2–4 before UI |
| 6. API save handler | `app/api/routers/ui.py` | Wires UI ↔ DB ↔ engine |
| 7. Integration tests | `tests/api/test_capital_grant_eligibility.py` | Validates step 6 |
| 8. UI form changes | `app/templates/partials/model_builder_line_form.html` + JS | User-facing |
| 9. S&U table yellow row | `app/templates/partials/sources_uses_table.html` | User-facing |
| 10. E2E tests | `tests/e2e/test_grant_eligibility_flow.py` | Full-stack validation |
| 11. Docs + deploy | `docs/FINANCIAL_MODEL.md`, `docs/DATA_MODEL.md`, prod deploy | Final |

---

## 11. Out of Scope

- Pro-rata grant allocation (deferred — stack position only)
- Indicator for over-cap grant (eligible Use total > grant max) — no UI change for that case
- Category-tag eligibility (`eligible_use_tags`) UI — engine retains, UI ignores
- Editing eligibility from Use side (always edit from Source side; junction maintained automatically)
- Multi-source / multi-Use waterfall optimization (linear programming) — keep stack-position greedy
