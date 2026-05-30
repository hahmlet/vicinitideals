# Bank Account Engine — Assessment & Implementation Plan

## Context

The model has no period-level bank account simulation from Close to Stabilization Start. The concern: are draws and reserves sized such that the cash balance never drops below the reserve floor during this window? A violation wouldn't be a user-configurable warning — it would be proof that the engine's reserve sizing is wrong.

---

## Status — 2026-05-30

**Shipped (engine primitives):**

| Commit | What | Files |
|---|---|---|
| `57fe0d3` | P2 + P3 (construction-phase rate lookup; carry on cumulative balance) | `app/engines/cashflow.py`, `app/engines/draw_schedule.py`, tests |
| `a7e4945` | P4 + P6 (single-draw source routing by stack position + eligible categories; UI filter + writeback fix for grants/equity) | `app/engines/draw_schedule.py`, `app/api/routers/ui.py`, tests |
| `a2b4785` | DrawScheduleInputs extension: opening_cash_balance, monthly_operating, stabilization_start_milestone | `app/engines/draw_schedule.py`, tests |
| `d852004` | Standalone `app/engines/bank_account.py` simulator (pure stateless, no engine coupling) | `app/engines/bank_account.py`, tests |

**Deferred / open:**
- **P1** (cashflow vs draw_schedule interest-model unification) — postponed; both engines run independently for different views and don't yet need to share an interest model
- **P5** (IR/LUR double-count fix) — my read of the code differs from the other agent's; flagged for separate review

**Not yet wired:**
- `compute_cash_flows` does NOT yet call `bank_account.simulate()` after sizing reserves
- No Cash Flow Support Reserve UseLineItem is emitted yet
- This is the integration step blocked by the size of the surgical change required to `cashflow.py` (3,846 lines)

### Update — 2026-05-30 (later)

- `a4649c6` extractor module shipped (B1)
- `52061c9` proof wired into `compute_cash_flows`, observation-only (B2)
- `cf086b3` wiring tests for the proof (B2c)
- `0b53a15` Cash Flow Support Reserve auto-emission shipped behind `BANK_ACCOUNT_RESERVE_ENABLED` flag (B3)
  - Default OFF — set the env var to `1` on VM 114 to enable
  - Engine upserts a "Cash Flow Support Reserve" UseLine sized to `max_shortfall`
  - Idempotent: creates / updates / removes itself based on each proof
  - `/compute` outer loop re-iterates when the reserve changes so Sources = Uses on the next pass
- **`<pending>` Persist proof on `OperationalOutputs.bank_account_proof` (migration 0102) + new Bank Account Proof KPI tile in the Underwriting view (B4)**
  - Aggregates the worst max_shortfall + min balance across projects
  - Green ✓ Solvent / red dollar gap when proof fails
  - Tooltip explains the proof window (CO → Stabilization Start)

### How to enable the auto-emission in production

```bash
# On VM 114, set the env var in the docker-compose override and restart:
mcp__proxmox-mcp__ssh_exec container_id=114 command="grep -q BANK_ACCOUNT_RESERVE_ENABLED /root/stacks/vicinitideals/.env || echo 'BANK_ACCOUNT_RESERVE_ENABLED=1' >> /root/stacks/vicinitideals/.env"
mcp__proxmox-mcp__ssh_exec container_id=114 command="cd /root/stacks/vicinitideals && docker compose up -d"
```

Disable by removing the env var (or setting to anything other than `1`).

---

## Prerequisite Fixes (Blocking)

Recent investigation by another agent surfaced four bugs that must be fixed before bank account integration is meaningful. The draw schedule output is currently unreliable — feeding it into cashflow.py would propagate errors.

### P1. cashflow.py and draw_schedule.py use different interest models

- cashflow.py: pre-funds IR at closing; balance stays flat (e.g. $13.8M), pool pays monthly interest
- draw_schedule.py: capitalizes interest into principal; balance grows (e.g. $13.9M → $15.8M)
- No IR concept exists in draw_schedule.py at all

**Required:** Pick one model as canonical. For deals with `carry_type="interest_reserve"`, the pre-funded pool is correct. draw_schedule.py needs an IR-aware mode that does NOT capitalize interest when the loan has a funded reserve.

### P2. Rate lookup bug in cashflow IR sizing

`total_constr_io` loop calls `_get_phase_carry(carry, "construction")` — looks for literal phase named `"construction"`. RJ Bond uses milestone-duration labels (`"IR"`, `"PI"`). Lookup returns None → falls back to 6% source rate instead of 5.5% schedule rate.

**Required:** Phase resolution must handle milestone-duration labels (IR, PI, etc.) OR carry schedules must normalize to canonical phase names. Bug overstates IR by ~9% on affected loans.

### P3. draw_schedule.py carry computed on wrong base

Computes carry on each incremental draw amount, not cumulative outstanding balance. Produces ~$79K total carry vs expected ~$1M+.

**Required:** Fix carry formula in `_calc_source_draws()` to multiply rate × cumulative balance per period, not rate × new draw amount.

### P4. draw_schedule.py does not honor existing routing infrastructure

**No new field needed.** The controls already exist:
- `CapitalModule.stack_position` (UI label: "Stack Position 1 = Most Senior") — `route_use_to_sources()` sorts by this for sequential draw order
- `CapitalModule.eligible_use_tags` (UI label: "Eligibility — check Uses this Source may fund") — `eligible_sources_for_use()` restricts routing
- `single_draw=True` for non-debt sources — emits lump-sum DrawEvent at activation

The bug: `cashflow.py` calls `route_use_to_sources()` (imports at line 42). `draw_schedule.py` does not — it runs its own sequential-payoff-chain logic that treats all sources as bridge→perm-style takeouts. That's wrong for a grant + senior debt capital stack.

Symptom: OR-MEP grant (Stack Position 1, eligible for Hard Costs only, $250K max) should fund the first $250K of Hard Costs, after which RJ Bond covers the rest. Today the draw schedule treats it as a payoff layer, inflating its draw to absurd amounts ($15.8M observed) and corrupting downstream sizing.

**Required:** Refactor `draw_schedule.py` to consume `route_use_to_sources()` like cashflow.py does. For each Use line per period, get the eligible sources sorted by stack_position, then fill each source up to its max before moving to the next. Equity/grant stubs with $0 max produce $0 draws naturally; no special-case filter needed.

### P6. draw_sources filter excludes funded grants; writeback corrupts equity rows

Current filter: `source_type == "debt"` — excludes OR-MEP grant (a funded source) while keeping zero-amount LP/GP equity stubs.

Also: writeback overwrites equity `draw_source.amount` with computed (inflated) values, making stub rows look like real configured sources on the next pass.

**Required:**
- Filter on `capital_module.source.amount > 0` (includes funded grants of any type, excludes $0 stubs)
- Stop writeback from overwriting equity draw_source amounts; debt-only writeback

Once P4 lands (draw_schedule honors `route_use_to_sources()`), this filter becomes simpler — eligibility + stack_position already handle source selection. P6 may collapse into P4 during refactor.

### P5. IR / Lease-Up Reserve double-dip (B10 / B13 split)

`_ir_lease_up_pool()` adds lease-up interest shortfall into the IR writeback. But that shortfall should sit in the Lease-Up Reserve (B13), not Interest Reserve (B10). Result: IR is overstated, B10 and B13 cover overlapping shortfalls.

**Required:** Remove lease-up pool from IR writeback. Lease-Up Reserve takes ownership of all lease-up shortfall coverage (operating + interest).

### Batching & Ordering

Two independent PRs:

**PR-IR (IR-focused, batch together for coherent audit trail):**
- P2 (rate bug 6% → 5.5%)
- P5 (B10/B13 split — remove `_ir_lease_up_pool` from IR writeback)
- One PR, one recalc on production deals, one clean before/after comparison

**PR-DRAW (draw schedule fixes):**
- P3 (carry on cumulative balance)
- P4 (parallel vs sequential source draw modes)
- P6 (draw_sources filter on amount > 0; stop equity writeback corruption)
- Wait for draw schedule findings to settle before opening this PR — more issues may surface

**P1 (interest model unification)** — resolved by construction when the unified period engine lands. Do not attempt to fix in current code; the duplication goes away when there's one engine.

Order: PR-IR can ship now (independent of draw schedule). PR-DRAW waits. Unified period engine designed in parallel with PR-DRAW investigation.

---

## Current State

### draw_schedule.py — Right Architecture, Wrong Scope

`app/engines/draw_schedule.py` already has a month-by-month simulation:
- `MonthlyCashFlow`: `draw_received`, `uses_paid`, `cash_balance`, `required_reserve`, `is_violation` per month
- `BalanceViolation` records + `DrawSchedule.is_valid` flag
- `_simulate_cash_balance()` (lines 413–502): the actual simulation loop
- Floors: `min_reserve_construction` and `min_reserve_operational` as config inputs

**Critical gap:** Simulation stops at CO (`operational_start_milestone = "co"`). Lease-up (CO → Stabilization Start) is NOT simulated — exactly the riskiest window.

### cashflow.py — Static Reserve Sizing Only

Three reserves sized as static lump sums funded at Close:

| Reserve | Sizing Method | Per-Period? |
|---------|---------------|-------------|
| Operating Reserve | `max(opex, DS) × months` | No — resets `cumulative_cash_flow` at Stabilization Start (line 677) |
| Interest Reserve | `period_interest_months()` + `_ir_lease_up_pool()` | No — pre-funded pool |
| Lease-Up Reserve | Perm DS during lease-up minus expected income | No — single lump sum |

Output: `periods: []` always empty. Only scalar summary metrics returned.

### The Disconnect

- draw_schedule.py's `min_reserve_operational` is config-passed — not derived from OR amount in cashflow.py
- The two engines size reserves independently; no joint proof of solvency
- Lease-up phase has no simulation at all

---

## The Correct Mental Model

If the engine is working correctly:
- Reserves (OR + IR + LUR) are funded at Close and sized to cover every shortfall
- Draws are sized to cover every construction use + carry
- Therefore: bank balance should never drop below the floor
- **A simulated violation = engine sizing bug, not a user input problem**

The bank account engine is a **proof mechanism**, not a warning system. If it shows a violation, that identifies a gap in the reserve formulas — the engine fixes its own sizing until the proof holds.

---

## The Gap

**Lease-up is not proven solvent:**

During lease-up (CO → Stabilization Start):
- Draws have stopped (construction draws are done)
- Income is ramping (occupancy 0% → stabilized over N months)
- Perm DS has started
- LUR is being consumed monthly to cover perm DS shortfalls
- If opex exceeds revenue early in lease-up before LUR fully covers it, there's a timing gap

The LUR sizing formula approximates the lease-up income shortfall using "phantom CF average, 60/40 split, opex 50→100%" (line 2966 notes). This is a heuristic, not a month-by-month proof. If the heuristic underestimates lease-up shortfalls, the bank balance could go negative in some months — but the engine wouldn't know.

**Also:** the draw schedule's `min_reserve_operational` floor is not set to the OR amount. These are sized independently.

---

## End-State Output (what the user sees)

A monthly table covering Close → Stabilization Start. Each row:

| Field | Source |
|---|---|
| Month | period_engine output |
| Beginning balance | prior period ending balance |
| Draws received (per source) | sized by Use timing + source draw_mode |
| Uses paid (per category) | Use line spread by `spread_months` / `active_from` / `active_to` |
| Interest charged (per loan) | rate × cumulative balance per period (day-precise) |
| Reserve activity | OR/IR/LUR balance changes |
| Ending balance | beginning + draws − uses − interest − reserve activity |
| Floor check | ending balance vs OR floor; PASS or VIOLATION |

Synthetic by design: hard costs spread evenly per `spread_months`, not actual draw cadence. Good enough for underwriting; real construction draws are lumpy in reality.

### Source routing example (no new UI controls)

User's deal: OR-MEP grant configured as Stack Position 1, Eligibility: All Hard Costs, $250K max.

After P4 + P6 fix the draw_schedule engine to honor existing infrastructure:

- Month 1 of Hard Costs: `route_use_to_sources()` returns `[OR-MEP grant, RJ Bond]` sorted by stack_position. Grant fills first up to $250K cap, RJ Bond covers shortfall.
- Subsequent months: grant fully consumed, RJ Bond covers 100% of remaining Hard Costs.
- Bank account table shows: grant $250K draw in Month 1, RJ Bond ramping across all construction months.
- RJ Bond's cumulative balance grows slower because grant funded the first $250K → less carry interest.

The UI already has the right controls (Stack Position, Eligibility). Only the engine needs the fix.

---

## Period Grain: Monthly

No daily cash flow tracker exists in the codebase. "Daily" appears only as:
- `interest.py:daily_rate()` — day-count conventions (`actual_360`, `actual_365`) for precise monthly interest math
- `draw_schedule.py` — day-precise spreading of uses into monthly buckets

Bank account engine works at **monthly grain with day-precise math inside each bucket**. This matches existing draws, debt service, reserves, tests, and reporting cadence. Daily simulation would add 30× compute for no underwriting-relevant precision.

---

## Target Behavior (User-Clarified)

The draw schedule's final state should be:

1. **Draws timed per Use settings** — each Use's `active_from` / `active_to` / `timing_type` determines when sources draw to cover it. No global heuristics.

2. **Interest follows draws** — carry computed on cumulative outstanding balance × rate per period. (Bug P3 above must be fixed.)

3. **Bank account simulation = invariant check, NOT auto-fix**
   - Simulate cash balance month-by-month using sized draws + scheduled uses + computed carry + reserve disbursements
   - At every period, balance should be ≥ reserve floor
   - **If gap detected: surface as engine diagnostic, do NOT auto-add a plug reserve**
   
   Example: end of June, bank should be at OR floor, but is $100K short. Wrong response: add $100K plug. Right response: surface "draw sizing under-funded period N by $100K" so the engine bug gets fixed.

4. **Cash Flow Support Reserve was wrong pattern — abandoned.** It would mask sizing bugs by silently topping up. The whole point of the bank account engine is to PROVE the sizing is right, not paper over it.

---

## Architecture Decision: Unified Period Engine

**Decision: Build a unified period engine. Both `draw_schedule.py` and `cashflow.py` consume it.**

### Why

Two engines today duplicate period-level math and have drifted apart (different interest models, disconnected sizing, no shared bank account view). Bolting a bank account check onto either side leaves the root cause — duplication — in place. Future bugs will recur. The unified engine eliminates the disconnection permanently.

### Design

New `app/engines/period_engine.py` owns:
- **Input:** Uses (with timing), Sources (with terms + draw_mode), Reserves (sized), Milestones, Interest schedules
- **Output:** Period rows (monthly), each containing: draws received per source, carry per source on cumulative balance, uses paid, reserve disbursements, bank balance start/end, floor check status
- **Invariant:** Every period bank balance ≥ reserve floor. Violation = engine diagnostic with period + source + gap details.

After unification:
- `draw_schedule.py` → thin layer that consumes periods and formats draw events for UI
- `cashflow.py` → thin layer that consumes periods and aggregates into IRR / DSCR / NOI summaries
- One interest model (P1 resolved by construction)
- One source of truth for floor enforcement
- One place to fix future bugs

---

## Implementation Plan

### Phase 1 — PR-IR (ship first, independent)

Bundle P2 + P5 into one IR-focused PR for a coherent audit trail:
- Fix `_get_phase_carry()` phase resolution to handle milestone-duration labels (`IR`, `PI`)
- Remove `_ir_lease_up_pool()` from IR writeback; Lease-Up Reserve takes ownership of lease-up shortfall
- Recalc affected production deals once; document before/after numbers in PR

### Phase 2 — Draw Schedule Investigation + PR-DRAW

- Let the draw schedule agent surface remaining findings
- When stable, ship P3 + P4 in one PR:
  - Fix carry base to cumulative balance × rate in `_calc_source_draws()`
  - Add `draw_mode` on CapitalModule; distinguish parallel vs sequential_payoff source handling

### Phase 3 — Design Unified Period Engine

In parallel with Phase 2 investigation:
- Spec `app/engines/period_engine.py` API and data model
- Map out which functions in cashflow.py and draw_schedule.py move into period_engine
- Identify test surface area to migrate
- Write design doc; review before implementation

### Phase 4 — Implement Period Engine

- Build `period_engine.py` with the unified period-row data model
- Migrate `cashflow.py` to consume periods (aggregation only)
- Migrate `draw_schedule.py` to consume periods (presentation only)
- Bank account invariant built in: any period with balance < floor raises engine diagnostic
- P1 (interest model conflict) resolved here by construction

### Phase 5 — Diagnostic Surfacing

Bank account violations surface in UI as engine errors (red banner / diagnostic panel), not user-resolvable warnings. Each diagnostic includes:
- Period date
- Expected floor
- Actual balance
- Implicated source(s) and uses
- Suggests which engine sizing function needs review

---

## Files Affected (by phase)

### Phase 1 (PR-IR)
- `app/engines/cashflow.py` — fix `_get_phase_carry()` phase resolution (P2); remove `_ir_lease_up_pool` from IR writeback, move shortfall coverage to LUR (P5)
- `tests/engines/test_cashflow.py` — phase resolution test for milestone-duration labels; IR/LUR ownership boundary test

### Phase 2 (PR-DRAW)
- `app/engines/draw_schedule.py` — fix carry base in `_calc_source_draws()` (P3); refactor to call `route_use_to_sources()` and honor stack_position + eligibility (P4); change source filter to `amount > 0` (P6); restrict writeback to debt sources only (P6)
- `tests/engines/test_draw_schedule.py` — carry on cumulative balance; grant-then-senior-debt routing using stack_position; eligibility whitelist respected; funded grant included; stub equity excluded; equity writeback no-op test

**No schema migration needed** — `stack_position`, `eligible_use_tags`, `eligible_module_ids` already exist on CapitalModule.

### Phase 3 (design)
- `docs/feature-plans/unified-period-engine.md` — NEW: design doc

### Phase 4 (implementation)
- `app/engines/period_engine.py` — NEW: single period-row source of truth
- `app/engines/cashflow.py` — refactor to consume period_engine (aggregation layer only)
- `app/engines/draw_schedule.py` — refactor to consume period_engine (presentation layer only)
- `tests/engines/test_period_engine.py` — NEW: period engine unit tests
- Existing engine test files restructure to validate aggregation/presentation layers only

---

## Verification

1. Bug fix tests (P2/P3/P4) pass with deterministic expected values
2. Run a deal known to currently produce a violation — confirm bank account check raises diagnostic identifying period + gap
3. Run a deal known to be correctly sized — confirm zero diagnostics
4. `uv run pytest tests/ -q --ignore=tests/e2e` — full suite green
5. Manual: load deal in production, intentionally underfund a reserve, confirm UI surfaces engine diagnostic (not a silent fix)
