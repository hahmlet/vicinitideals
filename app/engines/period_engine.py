"""
Period Engine — unified period-level interest math.

Owns: per-loan balance tracking, interest accrual/payment by carry type,
bank account floor enforcement.

Consumed by:
  cashflow.py   — aggregates PeriodRows into CashFlow ORM rows + DSCR/IRR/NOI
  draw_schedule.py — formats PeriodRow.loans into DrawEvent presentation

This is a pure stateless module: no DB access, no side effects.

Carry types
-----------
io_only
    Balance stays flat at principal. Monthly cash payment = P × rate/1200.
    Bank balance decreases each period by interest_paid.

interest_reserve
    Balance stays flat at principal. Interest is paid from a pre-funded IR pool,
    NOT from the operating bank account. Pool initialized at loan activation using
    linear draw-down sizing: P × rate/1200 × (N+1)/2 where N = active window months.
    Pool deficit (pool_close < 0) is flagged but does not reduce bank balance directly;
    it surfaces as a floor violation if operating cash cannot cover the gap.

capitalized_interest
    No cash payment. Balance accrues monthly: B_m = B_(m-1) × (1 + rate/1200).
    interest_paid = 0 each period. Bank balance unaffected by accrual.

pi (amortizing P&I)
    Standard amortization. Monthly payment = P × r × (1+r)^n / ((1+r)^n - 1).
    Interest component = balance × monthly_rate. Principal paid = payment - interest.
    Bank balance decreases each period by full monthly_pmt.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
ONE = Decimal("1")
_MONEY = Decimal("0.000001")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _d(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def compound_draw_sizing(
    uses_and_payoff: Decimal,
    opening_balance: Decimal,
    monthly_rate: Decimal,
    n_months: int,
) -> tuple[Decimal, Decimal]:
    """
    Self-referential draw sizing with compound interest.

    Sizes a draw D such that D covers uses_and_payoff plus compound carry on
    both the opening balance and the draw itself over n_months:
        D = (uses_and_payoff + B × (F-1)) / (2 - F)
        carry = (B + D) × (F - 1)
    where F = (1 + monthly_rate)^n_months.

    For n_months=1 this is algebraically identical to the simple-interest formula
        D = (uses + B×r) / (1 - r)
    so monthly-draw schedules are unaffected.

    Args:
        uses_and_payoff: uses_in_window + prior_source_payoff (direct costs to fund)
        opening_balance: cumulative debt balance before this draw
        monthly_rate: annual_rate / 1200
        n_months: draw window duration in months (draw_every_n_months)

    Returns:
        (total_draw, carry_cost)
    """
    if monthly_rate <= ZERO or n_months <= 0:
        return _q(uses_and_payoff), ZERO
    factor = (ONE + monthly_rate) ** n_months
    carry_on_existing = _q(opening_balance * (factor - ONE))
    denom = Decimal("2") - factor
    if denom < Decimal("0.0001"):
        denom = Decimal("0.0001")
    total_draw = _q((uses_and_payoff + carry_on_existing) / denom)
    carry_cost = _q((opening_balance + total_draw) * (factor - ONE))
    return total_draw, carry_cost


def _add_months(dt: datetime, months: int) -> datetime:
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

@dataclass
class PhaseSpec:
    period_type: str        # "construction" | "lease_up" | "stabilized" | "exit"
    n_months: int
    start_date: datetime | None = None


@dataclass
class LoanSpec:
    """
    One entry per debt module.

    active_from_period / active_to_period are 0-indexed month indices across all phases.
    The loan draws its full principal on active_from_period (no mid-window partial draws).
    """
    module_id: str
    carry_type: str         # "io_only" | "interest_reserve" | "capitalized_interest" | "pi"
    principal: Decimal
    rate_pct: Decimal       # Annual percent, e.g. Decimal("7.0") for 7 %
    active_from_period: int = 0
    active_to_period: int = 9_999
    amort_years: int = 30   # PI only; ignored for other carry types
    ir_pool_override: Decimal | None = None  # bypass computed pool amount


@dataclass
class PeriodEngineInputs:
    phases: list[PhaseSpec]
    loans: list[LoanSpec] = field(default_factory=list)
    uses_by_period: dict[int, Decimal] = field(default_factory=dict)
    operating_income_by_period: dict[int, Decimal] = field(default_factory=dict)
    operating_expenses_by_period: dict[int, Decimal] = field(default_factory=dict)
    reserve_floor_by_period: dict[int, Decimal] = field(default_factory=dict)
    opening_cash_balance: Decimal = ZERO


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

@dataclass
class LoanPeriodDetail:
    module_id: str
    carry_type: str
    balance_open: Decimal       # balance at start of period
    balance_close: Decimal      # balance at end of period (after accrual/amort)
    interest_accrued: Decimal   # CI only: amount added to balance
    interest_paid: Decimal      # IO/PI only: cash leaving bank account; IR/CI = 0
    ir_pool_open: Decimal       # IR only: pool balance at start of period
    ir_pool_close: Decimal      # IR only: pool balance at end of period
    principal_paid: Decimal     # PI only
    draw_received: Decimal      # funds received from this loan this period


@dataclass
class PeriodRow:
    period: int
    period_date: datetime | None
    period_type: str
    uses_paid: Decimal
    operating_income: Decimal
    operating_expenses: Decimal
    noi: Decimal
    loans: list[LoanPeriodDetail]
    total_interest_paid: Decimal    # bank-account cash outflow for interest (IO+PI only)
    total_debt_service: Decimal     # interest_paid + principal_paid
    bank_balance_open: Decimal
    bank_balance_close: Decimal
    reserve_floor: Decimal
    floor_violation: bool           # True when bank_balance_close < reserve_floor


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def run_period_engine(inputs: PeriodEngineInputs) -> list[PeriodRow]:
    """
    Pure function. Returns one PeriodRow per calendar month across all phases.
    Order matches phases order, then months within each phase.
    """
    # Build flat period sequence
    periods: list[tuple[int, str, datetime | None]] = []
    idx = 0
    for phase in inputs.phases:
        for m in range(phase.n_months):
            date = _add_months(phase.start_date, m) if phase.start_date else None
            periods.append((idx, phase.period_type, date))
            idx += 1

    # Pre-compute per-loan constants and initialize mutable state
    loan_states: dict[str, _LoanState] = {}
    for spec in inputs.loans:
        n_active = max(0, spec.active_to_period - spec.active_from_period + 1)
        loan_states[spec.module_id] = _LoanState.from_spec(spec, n_active)

    rows: list[PeriodRow] = []
    bank_balance = _d(inputs.opening_cash_balance)

    for period_idx, period_type, period_date in periods:
        loan_details: list[LoanPeriodDetail] = []
        total_interest_paid = ZERO
        total_principal_paid = ZERO
        total_draw_received = ZERO

        for spec in inputs.loans:
            detail = _compute_loan_period(
                spec,
                loan_states[spec.module_id],
                period_idx,
            )
            loan_details.append(detail)
            # IR interest comes from the pre-funded pool, not the operating account
            if spec.carry_type != "interest_reserve":
                total_interest_paid += detail.interest_paid
            total_principal_paid += detail.principal_paid
            total_draw_received += detail.draw_received

        uses = _d(inputs.uses_by_period.get(period_idx, ZERO))
        op_income = _d(inputs.operating_income_by_period.get(period_idx, ZERO))
        op_expenses = _d(inputs.operating_expenses_by_period.get(period_idx, ZERO))
        floor = _d(inputs.reserve_floor_by_period.get(period_idx, ZERO))
        noi = op_income - op_expenses

        bal_open = bank_balance
        bal_close = _q(
            bank_balance
            + total_draw_received
            + noi
            - uses
            - total_interest_paid
            - total_principal_paid
        )
        bank_balance = bal_close

        rows.append(PeriodRow(
            period=period_idx,
            period_date=period_date,
            period_type=period_type,
            uses_paid=uses,
            operating_income=op_income,
            operating_expenses=op_expenses,
            noi=noi,
            loans=loan_details,
            total_interest_paid=total_interest_paid,
            total_debt_service=total_interest_paid + total_principal_paid,
            bank_balance_open=bal_open,
            bank_balance_close=bal_close,
            reserve_floor=floor,
            floor_violation=bal_close < floor,
        ))

    return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class _LoanState:
    monthly_rate: Decimal
    balance: Decimal
    ir_pool: Decimal
    ir_pool_initial: Decimal
    monthly_pmt: Decimal    # PI only
    activated: bool

    @staticmethod
    def from_spec(spec: LoanSpec, n_active: int) -> _LoanState:
        monthly_rate = _d(spec.rate_pct) / Decimal("1200")
        principal = _d(spec.principal)

        if spec.carry_type == "interest_reserve":
            if spec.ir_pool_override is not None:
                ir_pool_initial = _d(spec.ir_pool_override)
            else:
                # Linear draw-down sizing: average balance = P × (N+1)/(2N)
                # Total interest = P × rate/1200 × (N+1)/2
                factor = Decimal(n_active + 1) / Decimal(2)
                ir_pool_initial = _q(principal * monthly_rate * factor)
        else:
            ir_pool_initial = ZERO

        if spec.carry_type == "pi":
            r = monthly_rate
            n = spec.amort_years * 12
            if r == ZERO or n == 0:
                monthly_pmt = _q(principal / Decimal(max(1, n)))
            else:
                factor = (ONE + r) ** n
                monthly_pmt = _q(principal * r * factor / (factor - ONE))
        else:
            monthly_pmt = ZERO

        return _LoanState(
            monthly_rate=monthly_rate,
            balance=ZERO,
            ir_pool=ZERO,
            ir_pool_initial=ir_pool_initial,
            monthly_pmt=monthly_pmt,
            activated=False,
        )


def _compute_loan_period(
    spec: LoanSpec,
    state: _LoanState,
    period_idx: int,
) -> LoanPeriodDetail:
    active = spec.active_from_period <= period_idx <= spec.active_to_period

    balance_open = state.balance
    ir_pool_open = state.ir_pool
    draw_received = ZERO
    interest_paid = ZERO
    interest_accrued = ZERO
    principal_paid = ZERO
    ir_pool_close = ir_pool_open

    # --- Activation ---
    if active and not state.activated:
        draw_received = _d(spec.principal)
        state.balance = draw_received
        balance_open = ZERO         # balance was 0 before this period
        state.ir_pool = state.ir_pool_initial
        ir_pool_open = ZERO         # pool was 0 before this period
        ir_pool_close = state.ir_pool_initial
        state.activated = True

    # --- Per-period interest math ---
    if active and state.activated:
        bal = state.balance
        r = state.monthly_rate

        if spec.carry_type == "io_only":
            interest_paid = _q(bal * r)

        elif spec.carry_type == "interest_reserve":
            interest_due = _q(bal * r)
            ir_pool_close = state.ir_pool - interest_due
            state.ir_pool = ir_pool_close
            # interest_paid stays ZERO — drawn from pool, not operating account

        elif spec.carry_type == "capitalized_interest":
            interest_accrued = _q(bal * r)
            state.balance = bal + interest_accrued
            # interest_paid stays ZERO

        elif spec.carry_type == "pi":
            interest_paid = _q(bal * r)
            principal_paid = max(ZERO, state.monthly_pmt - interest_paid)
            state.balance = max(ZERO, bal - principal_paid)

    balance_close = state.balance

    # --- Deactivation: reset state for subsequent periods ---
    if period_idx == spec.active_to_period:
        state.balance = ZERO
        state.activated = False

    return LoanPeriodDetail(
        module_id=spec.module_id,
        carry_type=spec.carry_type,
        balance_open=balance_open,
        balance_close=balance_close,
        interest_accrued=interest_accrued,
        interest_paid=interest_paid,
        ir_pool_open=ir_pool_open,
        ir_pool_close=ir_pool_close,
        principal_paid=principal_paid,
        draw_received=draw_received,
    )
