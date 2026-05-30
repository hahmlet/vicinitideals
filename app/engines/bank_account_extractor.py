"""Bank-account input extractor for the cashflow engine.

Given the already-computed CashFlow rows + UseLines + phase plan for a
project, builds the four input maps the bank-account simulator needs:

    months          — proof window, period-aligned month-start dates
    opening_cash    — sum of pre-funded "first_day" reserves at Close
    monthly_inflows — operating income per month (post-CO)
    monthly_outflows— opex + debt service per month (post-CO)
    monthly_floor   — required reserve floor per month

The extractor is intentionally narrow: it covers the OPERATING-phase proof
(CO → Stabilization Start). Construction-phase solvency is proven by the
draw_schedule engine, which already tracks month-by-month construction
draws, uses, and reserve floors.

Pure function. No DB I/O. No coupling to compute_cash_flows internals
beyond the row shape. Tests mock the inputs directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


_RESERVE_LABELS = {
    "Operating Reserve",
    "Interest Reserve",
    "Construction Interest Reserve",   # legacy alias
    "Pre-Development Interest Reserve",
    "Acquisition Interest Reserve",
    "Lease-Up Reserve",
    "Capitalized Construction Interest",
}


@dataclass
class BankAccountInputs:
    """The four maps the bank-account simulator consumes."""
    months: list[datetime] = field(default_factory=list)
    opening_cash: Decimal = Decimal("0")
    monthly_inflows: dict[datetime, Decimal] = field(default_factory=dict)
    monthly_outflows: dict[datetime, Decimal] = field(default_factory=dict)
    monthly_floor: dict[datetime, Decimal] = field(default_factory=dict)


def _to_dec(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _add_months(d: datetime, n: int) -> datetime:
    """Add n months to d (1st-of-month aligned)."""
    y, m = d.year, d.month + n
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return d.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def _month_start(d: date | datetime) -> datetime:
    if isinstance(d, datetime):
        return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return datetime(d.year, d.month, 1)


def extract_operating_proof_window(
    *,
    cash_flow_rows: list,                      # list[CashFlow] ORM rows
    use_lines: list,                            # list[UseLine] ORM rows
    first_period_date: datetime,               # period 0 anchor (deal start)
    co_period: int,                            # cash-flow row period at CO
    stabilized_period: int | None = None,      # row period at Stabilization Start; None = include all post-CO
    operating_reserve_amount: Decimal | None = None,  # OR floor; defaults to "Operating Reserve" UseLine
) -> BankAccountInputs:
    """Build bank-account simulator inputs for the OPERATING proof window.

    The window covers period[co_period] through period[stabilized_period - 1]
    inclusive (or through the last operating row if stabilized_period is None).

    cash_flow_rows must be ordered ascending by period. Each row supplies:
      - effective_gross_income → inflow
      - operating_expenses + debt_service → outflow

    Reserves are sourced from use_lines whose label is in _RESERVE_LABELS
    and whose timing_type indicates first-day funding. The sum becomes
    opening_cash.

    The floor map sets the Operating Reserve amount for every month at or
    after the CO row. Pre-CO months (if any are passed in) get a 0 floor.
    """
    rows_sorted = sorted(cash_flow_rows, key=lambda r: r.period)

    # Opening cash = sum of first-day reserves on UseLines.
    opening = Decimal("0")
    or_amount = Decimal("0")
    for ul in use_lines:
        label = getattr(ul, "label", "") or ""
        timing = getattr(ul, "timing_type", "") or ""
        amt = _to_dec(getattr(ul, "amount", 0))
        if timing not in ("first_day", "lump_sum"):
            continue
        if label in _RESERVE_LABELS:
            opening += amt
            if label == "Operating Reserve":
                or_amount = amt

    if operating_reserve_amount is not None:
        or_amount = operating_reserve_amount

    # Window bounds — only iterate rows inside the proof window. When
    # stabilized_period is None, include every row from co_period onward.
    if stabilized_period is None:
        # Sentinel = one past the highest period in the input
        window_end = (rows_sorted[-1].period + 1) if rows_sorted else co_period
    else:
        window_end = stabilized_period

    months: list[datetime] = []
    inflows: dict[datetime, Decimal] = {}
    outflows: dict[datetime, Decimal] = {}
    floor: dict[datetime, Decimal] = {}

    for row in rows_sorted:
        if row.period < co_period or row.period >= window_end:
            continue
        m = _add_months(_month_start(first_period_date), row.period)
        months.append(m)
        inflows[m] = _to_dec(row.effective_gross_income)
        outflows[m] = _to_dec(row.operating_expenses) + _to_dec(row.debt_service)
        floor[m] = or_amount

    return BankAccountInputs(
        months=months,
        opening_cash=opening,
        monthly_inflows=inflows,
        monthly_outflows=outflows,
        monthly_floor=floor,
    )


__all__ = [
    "BankAccountInputs",
    "extract_operating_proof_window",
]
