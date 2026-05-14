"""
newton_solve.py — Newton-Raphson DSCR-cap principal solver.

Replaces the closed-form _pv_from_pmt solve in dscr_capped / dual_constraint
sizing modes.  Convergence is typically 1-2 iterations because f(P) = DS(P)/NOI
is nearly linear in P for standard amortization.

Tolerance: |ΔP| < $1000  OR  |f(P)| < 0.001 DSCR units.
Iteration cap: 12.  Fallback to bisection after 3 consecutive Newton overshoots.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

log = logging.getLogger(__name__)

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
TWELVE = Decimal("12")
_TOLERANCE_P = Decimal("1000")
_TOLERANCE_DSCR = Decimal("0.001")
_ITER_CAP = 12
_OVERSHOOT_FALLBACK = 3

_q = Decimal("0.000001")


def _monthly_ds(principal: Decimal, rate_pct: Decimal, amort_years: int, io_months: int = 0) -> Decimal:
    """Stabilized-period monthly debt service for a given principal."""
    if principal <= ZERO:
        return ZERO
    r_annual = rate_pct / HUNDRED
    if amort_years <= 0 or r_annual <= ZERO:
        # IO-only: interest only, no amortization
        return (principal * r_annual / TWELVE).quantize(_q)
    r_m = r_annual / TWELVE
    n = amort_years * 12
    # Standard P&I formula: P × r / (1 − (1+r)^-n)
    factor = r_m / (ONE - (ONE + r_m) ** (-n))
    return (principal * factor).quantize(_q)


def _dscr(principal: Decimal, noi_annual: Decimal, rate_pct: Decimal, amort_years: int, io_months: int = 0) -> Decimal:
    ds_annual = _monthly_ds(principal, rate_pct, amort_years, io_months) * TWELVE
    if ds_annual <= ZERO:
        return Decimal("999")
    return (noi_annual / ds_annual).quantize(_q)


def solve_principal_for_dscr(
    noi_annual: Decimal,
    target_dscr: Decimal,
    rate_pct: Decimal,
    amort_years: int,
    io_months: int = 0,
    ltv_cap: Decimal | None = None,
) -> Decimal:
    """Return max loan principal where DSCR ≥ target_dscr.

    Newton-Raphson with bisection fallback.  Returns the Newton/bisection result
    clamped to ltv_cap if provided.  Returns ZERO when noi_annual or rate_pct ≤ 0.
    """
    if noi_annual <= ZERO or rate_pct <= ZERO or target_dscr <= ZERO:
        return ZERO

    # Initial guess: closed-form PV at target DS
    target_monthly_ds = noi_annual / target_dscr / TWELVE
    r_m = rate_pct / HUNDRED / TWELVE
    n = amort_years * 12
    if n > 0 and r_m > ZERO:
        factor = r_m / (ONE - (ONE + r_m) ** (-n))
        p0 = (target_monthly_ds / factor).quantize(_q)
    else:
        p0 = (target_monthly_ds * TWELVE / (rate_pct / HUNDRED)).quantize(_q) if rate_pct > ZERO else ZERO

    if p0 <= ZERO:
        return ZERO

    p = p0
    consecutive_overshoots = 0
    lo = ZERO
    hi = p * Decimal("3")  # safe upper bracket

    for i in range(_ITER_CAP):
        current_dscr = _dscr(p, noi_annual, rate_pct, amort_years, io_months)
        f = current_dscr - target_dscr

        if abs(f) < _TOLERANCE_DSCR:
            break

        # Update bracket
        if f > ZERO:
            lo = p  # current P gives DSCR too high → can increase P
        else:
            hi = p  # current P gives DSCR too low → must decrease P

        # Newton step: since DS ≈ k×P, DSCR ≈ NOI/(k×P×12), f'(P) ≈ -DSCR/P
        if p > ZERO:
            fp = -current_dscr / p
        else:
            break

        if fp == ZERO:
            break

        delta = -(f / fp)

        p_new = p + delta

        # Check for overshoot (outside bracket)
        if p_new < lo or p_new > hi:
            consecutive_overshoots += 1
            if consecutive_overshoots >= _OVERSHOOT_FALLBACK:
                # Fall back to bisection
                p_new = (lo + hi) / Decimal("2")
                consecutive_overshoots = 0
                log.info("newton_solve: bisection fallback at iteration %d, p=%.0f", i, float(p))
        else:
            consecutive_overshoots = 0

        if abs(p_new - p) < _TOLERANCE_P:
            p = p_new
            break

        p = p_new

    else:
        log.info(
            "newton_solve: hit iteration cap (dscr=%.4f target=%.4f p=%.0f)",
            float(_dscr(p, noi_annual, rate_pct, amort_years, io_months)),
            float(target_dscr),
            float(p),
        )

    result = p.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if ltv_cap is not None and ltv_cap > ZERO:
        result = min(result, ltv_cap)

    return max(result, ZERO)
