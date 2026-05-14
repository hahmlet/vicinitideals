"""
interest.py — day-precise interest accrual helpers.

Three day-count conventions:
  actual_360  (default)  daily_rate = annual / 360, actual elapsed days
  actual_365             daily_rate = annual / 365, actual elapsed days
  30_360                 every month = 30 days, year = 360 days

When only month counts are available (auto-sizing before calendar dates
resolved) use ``period_interest_months`` which assumes 30-day months.

Floating-rate scaffold: ``RateSeries`` wraps an index curve so callers
can pass either a scalar Decimal or a RateSeries — ``daily_rate`` and
``accrued_interest`` accept both.  Phase F ships with flat-curve stub;
real index data (SOFR, PRIME) is a future enhancement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

ZERO = Decimal("0")
_q_places = Decimal("0.000001")

CONVENTIONS = frozenset({"actual_360", "actual_365", "30_360"})
DEFAULT_CONVENTION = "actual_360"


@dataclass
class RateSeries:
    """Floating-rate specification. Phase F stub: index_curve holds a flat value."""
    index_ref: str                         # e.g. "SOFR_1M", "PRIME"
    spread_pct: Decimal = ZERO             # spread over index
    reset_frequency: str = "monthly"       # monthly | quarterly | annually
    index_curve: dict[date, Decimal] = field(default_factory=dict)

    def rate_on(self, as_of: date) -> Decimal:
        """Return annual rate (pct) for the given date.

        Walks backward through index_curve for the most-recent entry; falls
        back to spread_pct alone when the curve is empty (stub behavior).
        """
        if not self.index_curve:
            return self.spread_pct
        # Latest curve entry on or before as_of
        candidates = [d for d in self.index_curve if d <= as_of]
        if not candidates:
            base = next(iter(self.index_curve.values()))
        else:
            base = self.index_curve[max(candidates)]
        return base + self.spread_pct


RateInput = Decimal | RateSeries


def _scalar_rate(rate_input: RateInput, as_of: date | None = None) -> Decimal:
    """Resolve RateInput to a scalar annual rate percentage."""
    if isinstance(rate_input, RateSeries):
        return rate_input.rate_on(as_of or date.today())
    return Decimal(str(rate_input))


def daily_rate(
    rate_input: RateInput,
    convention: str = DEFAULT_CONVENTION,
    as_of: date | None = None,
) -> Decimal:
    """Daily interest rate for a given annual rate and day-count convention.

    Returns a Decimal fraction (e.g. 0.000222... for 8% Actual/360).
    """
    annual_pct = _scalar_rate(rate_input, as_of)
    if annual_pct <= ZERO:
        return ZERO
    annual = annual_pct / Decimal("100")
    if convention == "actual_365":
        return annual / Decimal("365")
    if convention == "30_360":
        return annual / Decimal("360")  # same divisor; day-count differs in accrual
    # default: actual_360
    return annual / Decimal("360")


def accrued_interest(
    principal: Decimal,
    start: date,
    end: date,
    rate_input: RateInput,
    convention: str = DEFAULT_CONVENTION,
) -> Decimal:
    """Interest accrued on principal from start (inclusive) to end (exclusive).

    Conventions:
      actual_360  actual calendar days / 360
      actual_365  actual calendar days / 365
      30_360      every month = 30 days, year = 360 (ISDA 30/360 Bond Basis)
    """
    if principal <= ZERO or start >= end:
        return ZERO

    if convention == "30_360":
        days = _days_30_360(start, end)
        annual_pct = _scalar_rate(rate_input, start)
        return _q(principal * annual_pct / Decimal("100") * Decimal(days) / Decimal("360"))

    actual_days = (end - start).days
    if actual_days <= 0:
        return ZERO

    if isinstance(rate_input, RateSeries) and rate_input.index_curve:
        # Floating rate: walk reset boundaries within [start, end)
        total = ZERO
        cursor = start
        while cursor < end:
            rate_here = rate_input.rate_on(cursor)
            next_reset = _next_reset(cursor, rate_input.reset_frequency)
            seg_end = min(next_reset, end)
            seg_days = (seg_end - cursor).days
            denom = Decimal("365") if convention == "actual_365" else Decimal("360")
            total += _q(principal * rate_here / Decimal("100") * Decimal(seg_days) / denom)
            cursor = seg_end
        return total

    annual_pct = _scalar_rate(rate_input, start)
    denom = Decimal("365") if convention == "actual_365" else Decimal("360")
    return _q(principal * annual_pct / Decimal("100") * Decimal(actual_days) / denom)


def period_interest_months(
    principal: Decimal,
    n_months: int,
    rate_input: RateInput,
    convention: str = DEFAULT_CONVENTION,
    draw_schedule: str = "lump",
) -> Decimal:
    """Interest accrued over N months when actual dates are not available.

    Assumes 30 days/month for all conventions.

    draw_schedule:
      "lump"     — principal drawn in full at month 0 → total = P × rate/12 × N
      "linear"   — principal drawn evenly each month  → total = P × rate/12 × (N+1)/2
    """
    if principal <= ZERO or n_months <= 0:
        return ZERO
    annual_pct = _scalar_rate(rate_input)
    if annual_pct <= ZERO:
        return ZERO

    # For month-count approximations, treat 1 month = 30 days
    denom = Decimal("360") if convention in ("actual_360", "30_360") else Decimal("365")
    monthly_rate = annual_pct / Decimal("100") / Decimal("12")
    # Adjust for non-standard day count: actual_365 rate is slightly different
    if convention == "actual_365":
        monthly_rate = annual_pct / Decimal("100") * Decimal("30") / Decimal("365")

    if draw_schedule == "linear":
        # Average outstanding balance = P × (N+1) / (2N) for even monthly draws
        factor = Decimal(n_months + 1) / Decimal(2)
    else:
        factor = Decimal(n_months)

    return _q(principal * monthly_rate * factor)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _q(v: Decimal) -> Decimal:
    return v.quantize(_q_places)


def _days_30_360(start: date, end: date) -> int:
    """ISDA 30/360 Bond Basis day count."""
    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year
    d1 = min(d1, 30)
    if d1 == 30:
        d2 = min(d2, 30)
    return 360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)


def _next_reset(cursor: date, frequency: str) -> date:
    """Next rate reset date after cursor."""
    from calendar import monthrange
    if frequency == "monthly":
        m = cursor.month % 12 + 1
        y = cursor.year + (cursor.month // 12)
        return date(y, m, 1)
    if frequency == "quarterly":
        offset = (3 - cursor.month % 3) % 3 + 3
        m = (cursor.month - 1 + offset) % 12 + 1
        y = cursor.year + (cursor.month - 1 + offset) // 12
        return date(y, m, 1)
    if frequency == "annually":
        return date(cursor.year + 1, cursor.month, 1)
    return date(cursor.year + 1, cursor.month, 1)
