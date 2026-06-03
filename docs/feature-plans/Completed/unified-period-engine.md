# Unified Period Engine — Design Document

**Status:** Design  
**Branch:** `feature/unified-period-engine`  
**Supersedes:** `bank-account-engine.md` § "P1 — interest model unification" and § "Architecture Decision: Unified Period Engine"

---

## Problem

`cashflow.py` and `draw_schedule.py` compute period-level interest math independently and disagree:

| Aspect | cashflow.py | draw_schedule.py |
|---|---|---|
| Interest Reserve carry | Pre-funds IR pool at close (`P × r/12 × (N+1)/2`); monthly flat-balance payments drawn from pool | Absent — `funded_carry=True` zeroes the carry term when an IR UseLine is present; no pool tracked |
| Capitalized Interest carry | Pre-sizes CI once at close (`P × r/12 × N`); adds to perm principal; no per-period accrual | Self-referential formula: `D = (U + B×r×n) / (1 − r×n)`; balance grows incrementally each draw |
| IO-Only carry | Monthly flat payment: `P × r / 1200` | Not modeled (only sized draws; no monthly amortization) |
| PI carry | Standard amortization: `P × r × (1+r)^n / ((1+r)^n − 1)` | Not modeled |
| Period granularity | Monthly (one row per month) | Draw-event (one row per draw, typically monthly or quarterly) |
| Balance tracking | Static for IR/IO; pre-grown perm for CI; declining for PI — **no per-loan running balance in loop** | Increments on draw date; static between draws |

Consequences:
- Draw schedule UI and cashflow model show different carry totals for the same loan
- Bank account proof (which reads from cashflow) and draw schedule can disagree on whether a floor is breached
- Bugs in either engine must be fixed twice
- P1 (from bank-account-engine.md) remains open; the bank account proof is correct only when its source cashflow rows are accurate

---

## Decision: cashflow.py's interest model is canonical

cashflow.py already drives all deal metrics (DSCR, IRR, NOI, equity waterfall). draw_schedule.py is a sizing and presentation aid. The unified engine will use cashflow.py's monthly-row model — not draw_schedule.py's event model — as the period loop substrate.

**Why not draw_schedule.py's capitalization model:**
- It cannot represent IO-only or PI carry types (no monthly amortization concept)
- It produces draw events, not monthly rows; bank account proof requires monthly rows
- Self-referential solve `D = (U + B×r×n) / (1 − r×n)` is a sizing shortcut, not a period-level tracker

**IR pool decision:** The pre-funded IR pool (cashflow.py's model) is correct US CRE practice. The unified engine will track an explicit IR pool balance per loan, drawn monthly. draw_schedule.py will read the pool amounts as pre-computed inputs rather than deriving them independently.

---

## Unified Period Row Schema

New dataclass `PeriodRow` in `app/engines/period_engine.py`:

```python
@dataclass
class LoanPeriodDetail:
    module_id: str
    carry_type: str          # io_only | interest_reserve | capitalized_interest | pi
    balance_open: Decimal    # Opening balance this period
    balance_close: Decimal   # Closing balance (after accrual/amortization)
    interest_accrued: Decimal  # For CI: amount added to balance
    interest_paid: Decimal   # For IR/IO/PI: cash leaving the account
    ir_pool_open: Decimal    # IR pool balance, opening (0 for non-IR carry)
    ir_pool_close: Decimal   # IR pool balance, closing
    principal_paid: Decimal  # PI only; 0 for all others
    draw_received: Decimal   # Draw from this source this period

@dataclass
class PeriodRow:
    period: int              # 0-indexed month across all phases
    period_date: datetime    # First day of this month
    period_type: str         # construction | lease_up | stabilized | exit
    uses_paid: Decimal       # Total construction/capex uses this month
    operating_income: Decimal
    operating_expenses: Decimal
    noi: Decimal
    loans: list[LoanPeriodDetail]
    total_interest_paid: Decimal   # Sum of loan.interest_paid
    total_debt_service: Decimal    # interest_paid + principal_paid (cash DS)
    bank_balance_open: Decimal
    bank_balance_close: Decimal
    reserve_floor: Decimal
    floor_violation: bool
```

`CashFlow` (existing ORM) is derived from `PeriodRow` by aggregation. `DrawEvent` (existing draw_schedule output) is derived by filtering `PeriodRow.loans` for draw_received > 0 and formatting for UI.

---

## Per-Carry-Type Formulas (Canonical)

### IO-Only

```
balance_m = principal  (constant)
interest_paid_m = principal × rate / 1200
ir_pool = 0
```

### Interest Reserve

```
ir_pool_at_close = principal × rate / 1200 × (N+1)/2   [linear draw-down sizing]
balance_m = principal  (constant)
interest_paid_m = principal × rate / 1200               (drawn from ir_pool)
ir_pool_m = ir_pool_(m-1) − interest_paid_m
  → if ir_pool_m < 0: shortfall surfaced as bank account floor violation
```

During lease-up, if NOI > interest_paid, excess may top up the ir_pool (existing `_ir_lease_up_pool` logic, preserved).

### Capitalized Interest

```
balance_m = balance_(m-1) × (1 + rate/1200)
interest_accrued_m = balance_m − balance_(m-1)
interest_paid_m = 0  (no cash payment; PIK)
ir_pool = 0
```

On retirement: `retirement_amount = balance_at_payoff`. Perm loan DS computed on `retirement_amount`, not on the original pre-sized principal. **This corrects the current cashflow.py behavior** where CI is pre-sized once at close rather than accrued monthly.

### PI (Amortizing)

```
monthly_pmt = P × r × (1+r)^n / ((1+r)^n − 1)  where r = rate/1200, n = amort_months
interest_paid_m = balance_(m-1) × r
principal_paid_m = monthly_pmt − interest_paid_m
balance_m = balance_(m-1) − principal_paid_m
```

---

## Period Engine API

```python
# app/engines/period_engine.py

@dataclass
class LoanSpec:
    module_id: str
    carry_type: str
    principal: Decimal
    rate_pct: Decimal
    amort_years: int
    active_from_period: int   # 0-indexed month when loan activates
    active_to_period: int     # inclusive; after this, balance retired
    draw_schedule: str        # "lump" | "linear" (for IR sizing)
    ir_pool_override: Decimal | None = None  # pre-computed pool (for migration shim)

@dataclass
class PeriodEngineInputs:
    phases: list[PhaseSpec]        # period_type, n_months, start_date per phase
    loans: list[LoanSpec]
    uses_by_period: dict[int, Decimal]
    operating_income_by_period: dict[int, Decimal]
    operating_expenses_by_period: dict[int, Decimal]
    reserve_floor_by_period: dict[int, Decimal]
    opening_cash_balance: Decimal

def run_period_engine(inputs: PeriodEngineInputs) -> list[PeriodRow]:
    """
    Pure function. No DB access. No side effects.
    Returns one PeriodRow per calendar month across all phases.
    """
```

Stateless pure function — same contract as `bank_account.simulate()`. No SQLAlchemy, no Celery, no I/O.

---

## Engine Architecture After Unification

```
                    ┌─────────────────────────────┐
                    │      period_engine.py        │
                    │  run_period_engine(inputs)   │
                    │  → list[PeriodRow]            │
                    └──────────┬──────────────────┘
                               │ list[PeriodRow]
              ┌────────────────┼────────────────────┐
              ▼                ▼                    ▼
       cashflow.py       draw_schedule.py    bank_account.py
    aggregate to          format draw         floor proof
    CashFlow ORM rows,    events for UI,      (already
    DSCR/IRR/NOI          Draw Schedule       period-native)
    summaries             export
```

`cashflow.py` becomes an **aggregation layer**: sum `PeriodRow` fields into `CashFlow` ORM rows, then run DSCR/IRR/NOI/waterfall on the aggregated series. The monthly cashflow loop (`for phase in phases: for month in range(phase.months)`) is replaced by `run_period_engine()` + aggregation.

`draw_schedule.py` becomes a **presentation layer**: filter `PeriodRow.loans` for draw events, format `DrawEvent` output, run reserve floor violations. The self-referential sizing solve is replaced by reading `PeriodRow.loans[*].draw_received`.

**One exception — auto-sizing**: `_auto_size_debt_modules()` in cashflow.py needs the final balance at retirement to size the perm loan. Under the new model, perm loan principal = `retirement_amount` from the prior-phase loan's final `balance_close`. The auto-sizing loop must call `run_period_engine()` for the construction phase, read the retirement balance, then size the perm and re-run for the operation phase. This replaces the current algebraic divisor fold-in.

---

## Migration Strategy

This is a large refactor. Incremental phases to keep main green throughout:

### Phase A — Build `period_engine.py` (no consumers yet)

1. Implement `run_period_engine()` with all 4 carry types
2. Full unit test suite (each carry type; IR pool exhaustion; CI accrual; PI amortization; multi-loan; floor violation)
3. No changes to cashflow.py or draw_schedule.py
4. Merge as soon as tests green — pure additive

### Phase B — Wire `draw_schedule.py` to consume period engine

1. `draw_schedule.py` calls `run_period_engine()` for the construction window only
2. Replace self-referential formula with `PeriodRow.loans[*].draw_received`
3. `DrawEvent` format derived from period rows
4. Backward-compat: public `compute_draw_schedule()` API unchanged
5. Test: draw totals must match pre-refactor output within $1 on all regression scenarios

### Phase C — Wire `cashflow.py` to consume period engine

1. Replace inner monthly loop with `run_period_engine()` call
2. Aggregate `PeriodRow` → `CashFlow` ORM row mapping
3. **CI correction applies here**: perm principal = retirement balance (may change carry totals on CI deals — acceptable; new numbers are correct)
4. Auto-sizing loop updated: run construction phase via period engine → read retirement balance → size perm → run full model
5. Backward-compat: all router-layer APIs unchanged
6. Test: 8-test Phase B debt regression suite must pass; DSCR/IRR/NOI within rounding on IO and PI deals

### Phase D — Remove dead code

1. Delete `_monthly_io()`, `_monthly_pmt()`, `_compute_preop_carry_cost()` from cashflow.py (logic now in period_engine.py)
2. Delete self-referential formula block from draw_schedule.py
3. Delete IR pool sizing in `_ir_lease_up_pool()` (period_engine.py owns this)

---

## Known Behavior Changes

| Area | Before | After |
|---|---|---|
| CI carry — total cost | Pre-sized at close: `P × r/12 × N` (lump) | Monthly compound accrual: `P × (1+r/1200)^N − P` (slightly higher for long windows) |
| CI carry — perm principal | `principal + pre_sized_CI` | `principal × (1+r/1200)^N` (same amount, derived correctly) |
| Draw schedule — carry | Self-referential approximation | Period engine exact monthly values |
| Bank account floor | Proof reads aggregated cashflow rows | Proof reads period rows directly (more precise) |
| IO/PI in draw schedule | Not modeled | Modeled (new capability) |

CI total cost change is a **correctness improvement**, not a regression. The pre-sized approximation and the monthly compound formula agree to <0.1% for typical construction windows (12–18 months) and diverge more for longer windows. Deals in production will see small carry-total updates on first recompute after migration.

---

## Not In Scope

- Treasury yield curve auto-fetch (float earnings uses user-entered rate; unchanged)
- Equity waterfall (operates on aggregated cashflow series; no change)
- Sensitivity analysis (operates on final metrics; no change)
- Excel export format
- Any UI changes (draw schedule UI reads same `DrawEvent` format post-migration)

---

## Test Plan

### Phase A (period_engine.py unit tests — `tests/engines/test_period_engine.py`)

| Test | Asserts |
|---|---|
| `test_io_carry_flat_balance` | Balance constant; monthly payment = P × r/1200 |
| `test_ir_carry_pool_drawn_monthly` | Pool decreases by interest each month; balance flat |
| `test_ir_pool_exhaustion_flags_violation` | floor_violation=True when pool < 0 |
| `test_ci_carry_compounds_monthly` | balance_m = P × (1+r/1200)^m |
| `test_ci_no_cash_payment` | interest_paid = 0 every period |
| `test_pi_amortization_schedule` | Monthly payment constant; balance declines to 0 |
| `test_pi_interest_principal_split` | Sum of principal_paid = P at end of amort_years |
| `test_multi_loan_periods` | Two loans with different active windows; each tracked independently |
| `test_bank_balance_tracks_inflows_outflows` | Opening + draws − uses − interest_paid = closing |
| `test_floor_violation_detected` | floor_violation when bank_balance_close < reserve_floor |

### Phase B (draw_schedule regression)

Run existing `tests/engines/test_draw_schedule.py` — all must pass post-refactor.

### Phase C (cashflow regression)

Run `scripts/test_phase_b_debt.py` — all 8 tests must pass.

### CI impact

Phase A: additive only — existing CI unchanged.  
Phase B: draw_schedule tests run in full gate.  
Phase C: Phase B regression suite added to full gate CI.
