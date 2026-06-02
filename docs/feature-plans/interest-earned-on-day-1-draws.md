# Interest Earned on Day-1 Draws (T-Bond Float Earnings)

## Context

Some capital sources — most importantly tax-exempt construction bonds — must draw 100% of proceeds at closing. The cash then sits in an account earning Treasury yield until it's deployed against construction Uses over the construction period. Today the engine has no concept of this float income. The user attempted to model it on deal `cf0e77c3-a445-434c-8788-6d948303d916` (project `c1e823ce-c406-4aa0-8d25-633b9dca12f4`) by creating a workaround "Interest Earned Back" source that draws at Lease-Up. That breaks because (a) it leaks into reserve sizing as if the cash were freely available, (b) it has no eligibility constraints, (c) it pollutes the waterfall as if it were equity.

The desired behavior is direct and conservative: estimate float income from a user-entered Treasury yield × the running balance of the parent source, and return that income to the project in only two restricted ways — a Developer Fee top-up after construction is complete, and/or a voluntary debt principal paydown. **Reserves (IR, OR, LUR, CFSR) must continue to be sized as if this money does not exist** because we cannot reliably time T-bond secondary-market sales to construction draw needs.

This plan introduces a new capital vehicle (`vehicle_type="float_earnings"`), wires it through cashflow, source routing, debt-paydown, and Dev Fee balance tracking, and follows the bank-account-proof persistence pattern that landed in commits `127c030` / `3fedba1` / `ae076d2` / `3575f1c` / `0686277` (see [docs/FINANCIAL_MODEL.md](../FINANCIAL_MODEL.md) Appendix G).

## Prerequisite P0 — Interest Reserve must respect `draw_type` first

The IR Use writer currently hardcodes flat `principal × rate/12 × N` math (equivalent to `draw_schedule="lump"` regardless of input), while the principal solver was retrofitted to read `draw_type`. The two paths diverge. This means IR sizing today is wrong for `draw_type="draw_down"` sources, and any float-earnings work would compound the error.

**Fix is one line**: in [app/engines/cashflow.py](../../app/engines/cashflow.py), replace the flat multiply with `period_interest_months(p3, _n_constr3, cr3, draw_schedule=_draw_schedule_for(_carry3_ct, src3.get("draw_type")))`. Add a regression test asserting IR Use amount differs between two scenarios (`fully_drawn` vs `draw_down`, same principal/rate/N). **Land this before any float-earnings phase.** Owner: separate session in progress.

## Recommended approach

A 5th `vehicle_type` value (`float_earnings`) keyed to a parent capital module, with a small dedicated engine module that derives a monthly running balance and an income series. Strict eligibility (whitelist of two cost categories) keeps the source out of the waterfall and out of reserve sizing. Application of earnings is split by user-entered % between Dev Fee top-up and debt principal paydown, applied at a user-chosen milestone against a user-chosen debt module.

### Product decisions (confirmed)

| Decision | Choice |
|---|---|
| Yield curve source | User-entered annual % on the float-earnings source itself |
| Application | Splittable % between Dev Fee top-up and debt paydown (must sum to 100; default 100/0 user-chosen) |
| Trigger | Parent source has `draw_type=fully_drawn` AND new flag `balance_earns_interest=true` |
| Paydown timing | User picks a milestone (e.g., Construction Complete) |
| Paydown target | User picks one debt module via dropdown |
| Dev Fee top-up mechanism | Modeled as accrued/paid balance on a tracked Dev Fee balance (couples to in-flight Dev Fee enhancement) |

## Phasing

The Dev Fee top-up path depends on Dev Fee being tracked as its own balance — that work is part of the in-flight [developer-fee-multi-source](developer-fee-multi-source.md) plan. To avoid blocking, ship in two phases.

- **Phase A (this plan, ship first):** debt-paydown path complete; Dev Fee top-up path is gated (split must currently be 100/0 in favor of debt paydown). UI exposes the dev-fee split field but disabled with tooltip "Available once Dev Fee balance modeling ships."
- **Phase B (lands with Dev Fee enhancement):** Dev Fee top-up path enabled, percent split free, integration with `dev_fee_binding_context` and the funded/deferred split.

## Critical files to modify

### Model + schema
- [app/models/capital.py](../../app/models/capital.py) — add `VehicleType.FLOAT_EARNINGS = "float_earnings"` to the enum at lines 24–29. No new columns needed; data lives in the existing JSONB `source` column.
- [app/schemas/capital.py](../../app/schemas/capital.py) — `CapitalSourceSchema` already carries `extra="allow"`, but declare these explicitly for type safety:
  - `parent_module_id: UUID | None` (the source whose balance earns float)
  - `yield_pct: Decimal` (annual)
  - `dev_fee_split_pct: Decimal` (0–100; Phase A: forced to 0)
  - `debt_paydown_split_pct: Decimal` (0–100; must sum with above to 100; Phase A: forced to 100)
  - `paydown_debt_module_id: UUID | None`
  - `paydown_milestone_id: UUID | None`
  - On any source: `balance_earns_interest: bool` (defaults False)

### Engine — new module
- **Create [app/engines/float_earnings.py](../../app/engines/float_earnings.py)** with:
  - `compute_float_balance_schedule(parent_source_drawn: Decimal, monthly_construction_uses: list[Decimal], yield_pct: Decimal) -> list[FloatBalanceRow]` — derives month-by-month balance: open balance = day-1 draw; each month subtract construction spend allocated to the parent source, then add `prior_balance × yield_pct / 12` as that month's earnings.
  - `total_float_earnings(scenario) -> Decimal` — aggregates across all enabled float-earnings sources in the scenario.
  - `float_earnings_by_target(scenario) -> {debt_module_id: amount, dev_fee_balance: amount}` — applies the user-entered split.

### Engine — cashflow integration
- [app/engines/cashflow.py](../../app/engines/cashflow.py):
  - In the orchestration that runs after `_auto_size_debt_modules()` and before the bank-account proof, call into `float_earnings.compute_float_balance_schedule(...)`. Float earnings must NOT be fed back into the IR solver or any reserve sizer — they sit downstream of sizing.
  - Reuse the existing `_uses_in_window()` helper to extract construction-period spend for the parent source.
  - Confirm `_auto_size_debt_modules()` (reserve sizing) is blind to float income — the Phase 1 exploration confirmed it operates algebraically on principal/rate, not on operating cash. Add a unit test that locks this in.

### Engine — debt paydown
- **Create [app/engines/debt_paydown.py](../../app/engines/debt_paydown.py)** (or, if scope stays small, extend cashflow.py). At the user-chosen `paydown_milestone_id` period:
  - Reduce target debt module's outstanding balance by the paydown amount.
  - For amortizing (PI) loans, recompute the remaining amortization schedule from the new balance.
  - For IO loans, the paydown shrinks the balloon; recompute interest expense for periods after the paydown.
  - Surface the paydown as a capital event line item (pattern matches existing refi-proceeds logic at [cashflow.py:383–432](../../app/engines/cashflow.py#L383)).

### Engine — source routing
- [app/engines/source_routing.py](../../app/engines/source_routing.py) — float-earnings sources must be restricted by `eligible_use_tags` to a fixed whitelist:
  - `dev_fee_top_up` (Phase B only)
  - `debt_principal_paydown`
  - Engine sets these tags automatically on float-earnings sources; user cannot edit. This guarantees the source can never be applied to construction hard costs, equity, or reserves.

### Engine — waterfall
- [app/engines/waterfall.py](../../app/engines/waterfall.py) — no changes required. The waterfall's `_is_debt_module` / `_is_equity_module` helpers (around lines 1378–1385) filter by `vehicle_type in ("debt", "equity")`. `float_earnings` matches neither and will be ignored, which is the correct behavior (the cash is consumed by paydown / dev fee top-up before any equity distribution).

### Engine — dev fee (Phase B)
- [app/engines/dev_fee.py](../../app/engines/dev_fee.py) — extend to track an accrued/paid Dev Fee balance period-by-period. Float-earnings top-up applied at the paydown milestone increments the "paid" series. Integrate with `dev_fee_binding_context` from the [developer-fee-multi-source](developer-fee-multi-source.md) plan.

### Persistence
- New JSON column on `OperationalOutputs`: `float_earnings_series JSONB` — period-level `{period: {parent_module_id, balance, monthly_earnings}}`. Follows the `bank_account_proof` precedent.
- New Alembic migration `0104_float_earnings.py` (slot 0103 claimed by developer-fee-multi-source; rebase onto that branch before claiming a number): adds the enum value, adds the JSON column.

### API
- [app/api/routers/ui.py](../../app/api/routers/ui.py) — form handler around lines 6620–6790 already parses `draw_type` and `eligible_use_ids`. Extend to also parse the new fields (`balance_earns_interest`, `parent_module_id`, `yield_pct`, split %, `paydown_debt_module_id`, `paydown_milestone_id`). For float-earnings sources, force `eligible_use_tags` server-side regardless of client input.

### UI templates
- [app/templates/partials/model_builder_panel.html](../../app/templates/partials/model_builder_panel.html) — Sources table around lines 236–297. Add a visually distinct row style for `vehicle_type=float_earnings` (different badge color, "earned from: {parent label}" subtitle). Add float-earnings total to the Sources subtotal but flag it as "non-cash at close."
- [app/templates/partials/model_builder_line_form.html](../../app/templates/partials/model_builder_line_form.html) — capital module form around line 1223 (the existing `draw_type` dropdown):
  - On any source with `draw_type=fully_drawn`, expose a `balance_earns_interest` checkbox.
  - When `vehicle_type=float_earnings` selected, swap form to a dedicated layout: parent source dropdown, yield %, split sliders (Phase A: debt slider locked at 100), debt module dropdown, milestone dropdown.

### Docs
- Append **Appendix H — Float Earnings on Forced Day-1 Draws** to [docs/FINANCIAL_MODEL.md](../FINANCIAL_MODEL.md) covering the balance derivation, IR independence invariant, paydown application, and the Phase A / Phase B gating.

## Parent-source state transitions (compute-time only)

A float-earnings source depends on its parent (`parent_module_id` + parent's `draw_type=fully_drawn` + parent's `balance_earns_interest=true`) and on two soft FKs (`paydown_debt_module_id`, `paydown_milestone_id`). Any of these can break when the user edits the parent, deletes the parent, deletes the target debt module, or deletes the milestone.

**Rule: validate at compute time, surface as compute warnings, do nothing in the UI between recomputes.** The user must hit Re-Compute after any edit anyway — that's the natural moment to evaluate the float source. No live banners, no persisted dormant flags, no delete-confirmation modals.

At the start of `compute_float_balance_schedule()`, run `validate_float_source(scenario, source)`. For each broken precondition, produce a zero-impact result (no earnings, no paydown) and append a warning to the compute output. Warnings surface alongside existing engine warnings in the standard compute results panel.

| Broken precondition | Warning message |
|---|---|
| `parent_module_id` null or module missing | "Float-earnings source has no parent — no earnings computed." |
| Parent's `draw_type != fully_drawn` | "Float-earnings source paused: parent no longer draws at start." |
| Parent's `balance_earns_interest` is false | "Float-earnings source paused: parent has 'Balance Earns Interest' turned off." |
| `paydown_debt_module_id` missing or module deleted | "Float-earnings paydown skipped: target debt module missing." |
| `paydown_milestone_id` missing or milestone deleted | "Float-earnings paydown skipped: target milestone missing." |

Source row stays visible in the Sources table either way — user-entered config is preserved. If user fixes the precondition and recomputes, the source automatically resumes producing earnings on the next compute. No persisted state needed.

## Reusable infrastructure (do not reinvent)

| Need | Existing helper / pattern | Location |
|---|---|---|
| Apply paydown as a capital event | Refi-proceeds injection logic | [cashflow.py:383–432](../../app/engines/cashflow.py#L383) |
| Restrict source to specific Uses | `eligible_use_tags` + `route_use_to_sources()` | [app/engines/source_routing.py](../../app/engines/source_routing.py) |
| Convergence loop after engine emits new state | `summary["needs_recompute"] = True` pattern from bank-account proof | [cashflow.py:1086–1099](../../app/engines/cashflow.py#L1086) |
| Period-level JSON persistence | `OperationalOutputs.bank_account_proof` column | bank-account-proof commit `0686277` |
| Per-period extraction of Uses in a phase | `_uses_in_window()` | `cashflow.py` |
| Allowlist gating for new computed output | `BANK_ACCOUNT_RESERVE_ALLOWED_SCENARIOS` env var pattern | [cashflow.py:15–47](../../app/engines/cashflow.py#L15) — consider mirroring with `FLOAT_EARNINGS_ALLOWED_SCENARIOS` for a staged rollout |

## Verification

End-to-end checks before marking complete:

1. **IR independence (engine):** unit test in `tests/engines/test_float_earnings.py` — same deal, run with float earnings enabled and disabled. IR Use amount must be byte-identical between the two runs.
2. **Balance derivation (engine):** unit test asserting that for a $10M day-1 draw with $1M monthly construction spend over 10 months and 5% annual yield, the monthly earnings series matches a hand-computed table.
3. **Paydown affects debt balance (engine):** unit test confirming that at the paydown milestone, the target debt module's outstanding balance drops by the paydown amount and subsequent period DS reflects the new balance. Non-target debt modules are untouched.
4. **Sources = Uses invariant (regression):** `uv run python scripts/test_phase_b_debt.py --base-url https://viciniti.deals --auth tests/e2e/auth-state.json` must still pass.
5. **Routing (engine):** unit test confirming a float-earnings source cannot fund any Use other than the whitelisted categories, even if the user tries to set `eligible_use_tags` manually.
6. **API (integration):** `tests/api/test_capital.py` — POST a float-earnings module with valid fields, retrieve, update, delete.
7. **UI (E2E):** `tests/e2e/test_float_earnings_flow.py` — on the reference deal `cf0e77c3-a445-434c-8788-6d948303d916`, tick `balance_earns_interest` on the RJ Bond, add a float-earnings source with 4.30% yield and 100% paydown split targeted at the RJ Bond at the Construction Complete milestone. Assert (a) Sources table shows the new source with the right total, (b) IR Use amount is unchanged vs. baseline, (c) RJ Bond balance drops at the paydown milestone, (d) waterfall outputs are not contaminated by the float source.
8. **Manual smoke check on the live deal:** reproduce the original problem deal and confirm the workaround "Interest Earned Back" source can be deleted and replaced cleanly.

After tests pass: commit, push, deploy via `mcp__proxmox-mcp__ssh_exec container_id=114 command="bash /root/deploy-vicinitideals.sh"`, confirm health check.

## Out of scope (explicit)

- Treasury yield curve auto-fetch — user enters yield % manually. Revisit if multiple users want shared curves.
- Modeling T-bond maturity timing or acquisition fees — assumption is 100% secondary-market sale at face.
- Float earnings on equity capital sitting in escrow — only `vehicle_type` debt-like sources with `draw_type=fully_drawn` qualify in v1.
- Multi-debt paydown splits — single debt module per float source. Users wanting splits can create multiple float-earnings sources.
- Phase B Dev Fee integration details — owned by the [developer-fee-multi-source](developer-fee-multi-source.md) plan.
