# Float Earnings Phase B — Deferred Dev Fee Paydown via CF Waterfall

## Status

Plan. Not yet implemented.

## Context

Phase A (commit `0fd32dc`, 2026-06-02) shipped the float-earnings vehicle
type, balance math, validation, and a forced 100/0 split (100% to debt
paydown, 0% to dev fee). The UI exposes both sliders but the dev-fee one
is disabled with a tooltip pointing at this plan.

Phase A originally documented Phase B as blocked on the
"Multi-Source Developer Fee Phase 2 operating-cash sink"
(Appendix H.9), which envisioned a period-by-period accrued/paid
deferred Dev Fee balance with operating cash subordinated to it.

**That framing was wrong for this codebase.** Two corrections from
discussion 2026-06-02:

1. The cashflow engine does not model real operating losses. Every
   operating month is profitable by assumption — we are modeling
   "getting a project done," not real-world stabilized ops. So
   reserves never get drawn down in the simulation, and "refill
   reserves" is not a thing the CF waterfall has to do.
2. The Cash Flow Support Reserve (CFSR) was a stub idea, never meant
   to be active in production. It is feature-flagged off
   (`BANK_ACCOUNT_RESERVE_ENABLED` env var). It does not belong in
   the Phase B waterfall ordering at all.

The remaining demands on operating cash are therefore narrower than
Appendix H.9 implied:

1. **Debt service** (existing waterfall tier, one per debt module).
2. **Deferred Dev Fee paydown** (new tier, this plan).
3. **Equity residual** (existing).

Float-earnings paydown amounts become operating cash inflows at the
float source's `paydown_milestone_id`, then flow through the same
waterfall as any other surplus revenue.

## Decisions (confirmed)

| Question | Decision |
|---|---|
| Order in CF waterfall | Debt service → deferred Dev Fee paydown → equity residual. (No CFSR refill step — CFSR is a stub.) |
| Float earnings routing | Treat the float source's `dev_fee_split_pct` + `debt_paydown_split_pct` as a hint, but ultimately just inject the total at the paydown milestone as operating cash. The waterfall consumes it normally. UI should still let the user pre-split because they want to see "X paid to Dev Fee" surfaced in the source row. |
| CFSR fate | Out of scope for Phase B. Document as known-dead and queue a separate cleanup session. |
| Auto-seed `deferred_developer_fee` tier | Yes — when a scenario has any deferred Dev Fee balance > 0, auto-insert one tier between the last debt_service tier and the residual tier. User can edit / delete like any other tier. |

## Architecture

### Deferred Dev Fee balance — current state

`app/engines/dev_fee.py` already computes:

- `funded_at_close` — portion of total Dev Fee filled from the Source
  allowances at close.
- `deferred` — total Dev Fee minus `funded_at_close`. Persisted on
  `UseLine.dev_fee_binding_context` (display-only column on the auto
  Dev Fee row).

What's missing: a period-by-period **balance** schedule that tracks
the deferred amount as it gets paid down post-close.

### What Phase B adds

#### 1. Deferred Dev Fee balance series (engine)

**New helper in `app/engines/dev_fee.py`** (or a new
`app/engines/dev_fee_balance.py` if dev_fee.py is too heavy):

```python
def compute_deferred_balance_schedule(
    *,
    deferred_at_close: Decimal,
    paydowns_by_period: dict[int, Decimal],
    period_count: int,
) -> list[DeferredBalanceRow]:
    """Period-by-period: opening_balance, paydown_amount, closing_balance.

    Caller supplies `paydowns_by_period` aggregated from:
      - Waterfall deferred_developer_fee tier distributions
      - Float-earnings dev_fee_topup_amount injections at their milestone

    No interest accrual on the deferred balance in v1 (matches LIHTC
    typical treatment where deferred Dev Fee is non-accruing developer
    contribution).
    """
```

Persisted on `OperationalOutputs.dev_fee_balance_series JSONB` — same
shape pattern as `float_earnings_series` and `bank_account_proof`.

#### 2. Float earnings → operating cash injection (engine)

`app/engines/cashflow.py` already calls `compute_scenario_float_earnings`
post-sizing and synthesizes capital event line items. Phase A injects
`paydown_amount` as a debt principal reduction.

Phase B: also inject `dev_fee_topup_amount` at the paydown milestone as
**operating cash inflow** with `LineItemCategory.cash_flow_support` (or
new category `dev_fee_paydown_source` if we want it distinct). The
waterfall sees it as residual operating cash and routes it through the
deferred Dev Fee tier when one exists.

#### 3. Waterfall — consume `deferred_developer_fee` tier

`app/engines/waterfall.py` already iterates tiers in priority order
distributing operating cash. Add a new branch for
`tier_type == WaterfallTierType.deferred_developer_fee`:

```python
elif tier.tier_type == WaterfallTierType.deferred_developer_fee:
    # Pay down outstanding deferred balance from this period's
    # available cash. Capped at min(available_cash, balance_remaining).
    pay = min(period_cash_available, deferred_balance_remaining)
    distribute_to_dev_fee(tier, period, pay)
    deferred_balance_remaining -= pay
    period_cash_available -= pay
```

The Phase B implementation will need to thread the deferred balance
state through the waterfall's per-period loop. Pattern matches existing
debt_service tier handling.

#### 4. Auto-seed the deferred Dev Fee tier (engine)

In `app/engines/waterfall.py:_seed_default_tiers_if_empty()` (the
existing auto-seed block at lines 388–447):

- If scenario has a non-zero deferred Dev Fee amount AND no existing
  `deferred_developer_fee` tier, insert one at
  `priority = max(debt_service_priorities) + 1`, shifting the residual
  tier's priority by 1.
- Description: `"Auto: pay down deferred Developer Fee from operating
  cash"`.

User can delete this tier in the Waterfall editor; the engine respects
their choice on subsequent recomputes (does not re-create on every
compute — only seeds when tiers list is empty, matching existing
debt_service behavior).

#### 5. UI — lift the Phase A gate

`app/templates/partials/model_builder_line_form.html` Phase A note
disables the dev-fee split slider and shows the gating tooltip. Phase
B:

- Remove the `disabled` attribute and tooltip.
- Add a hint: *"Split how float earnings hit the deal: a % to debt
  principal paydown, a % to deferred Developer Fee paydown. The
  earnings still flow through the operating cash waterfall — this
  split decides which target they're labeled against on the milestone
  event row."*
- Default split: 0% dev fee / 100% paydown (preserves Phase A
  behavior for existing rows). Validation enforces sum to 100.

Explainer modal (`app/templates/partials/dev_fee_explainer_modal.html`)
gains a "Deferred balance schedule" section reading
`outputs.dev_fee_balance_series`.

### Migration

New `alembic/versions/0107_dev_fee_balance_series.py`:

- Add `operational_outputs.dev_fee_balance_series JSONB NULL`.
- No data backfill needed (series is recomputed on next deal recompute).

## Out of scope

- **CFSR cleanup**: separate session. CFSR continues to exist behind
  its feature flag but is documented as dead.
- **Operating-cash subordination beyond Dev Fee**: Appendix H.9
  envisioned a richer subordination scheme. With reserves not
  draining and no real operating loss model, the only sweep order
  Phase B needs is debt → deferred Dev Fee → equity. Anything more
  granular is YAGNI.
- **Per-period interest on Dev Fee deferred balance**: not accruing
  in v1 (LIHTC norm). If a deal type needs it, add as a separate
  feature later.
- **Reserve refill from operating cash**: by codebase assumption,
  reserves don't get drawn. Not a waterfall step.

## Files touched (summary)

| File | Change |
|---|---|
| `app/engines/dev_fee.py` (or new `dev_fee_balance.py`) | `compute_deferred_balance_schedule()` |
| `app/engines/cashflow.py` | Wire dev_fee_topup_amount as operating cash inflow at paydown milestone |
| `app/engines/waterfall.py` | New tier branch for `deferred_developer_fee`; auto-seed when deferred > 0 |
| `app/models/cashflow.py` | New `OperationalOutputs.dev_fee_balance_series` column |
| `app/templates/partials/model_builder_line_form.html` | Lift Phase A gate on dev-fee slider |
| `app/templates/partials/dev_fee_explainer_modal.html` | Deferred balance schedule section |
| `alembic/versions/0107_dev_fee_balance_series.py` | Migration |
| `tests/engines/test_dev_fee_balance.py` (new) | Balance schedule math + paydown ordering |
| `tests/engines/test_float_earnings.py` | Phase B integration |
| `tests/engines/test_waterfall.py` | Auto-seed + tier distribution |
| `docs/FINANCIAL_MODEL.md` | Update Appendix H.7/H.9 and Appendix I.4 |

## Verification

- Reference deal: `cf0e77c3-a445-434c-8788-6d948303d916` (the deal user
  used to inspect auto-created Uses).
- Targeted E2E: `tests/e2e/test_underwriting_flow.py` covers the dev
  fee + waterfall surfaces.

## Open questions

None blocking — all decisions above are confirmed.
