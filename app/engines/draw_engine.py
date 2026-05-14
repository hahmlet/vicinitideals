"""
draw_engine — per-period capital draw inflow computation.

Phase E: replaces the month-0 total_sources lump-sum pre-seed in cashflow.py.
Capital is drawn incrementally as uses fire each period.

Non-BALANCE_ONLY uses: draw matches use outflow timing (lump on period 0 or
spread across phase months).

BALANCE_ONLY uses (Operating Reserve, CI/IR reserves, Lease-Up Reserve): drawn
as a single inflow at the first month of their funding phase.  They are excluded
from capital_outflow in NCF so the balance reflects "reserves still on hand".
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engines.cashflow import PhaseSpec


ZERO = Decimal("0")
_q_places = Decimal("0.000001")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_q_places)


def compute_period_draw_inflow(
    phase: Any,
    month_index: int,
    use_lines: list[Any],
    use_line_phase_overrides: dict[Any, Any] | None,
    balance_only_labels: set[str],
    use_line_phase_map: dict[str, set[Any]],
) -> Decimal:
    """Return total capital drawn inflow for this period.

    Non-BALANCE_ONLY uses: draw = use outflow (same timing).
    BALANCE_ONLY reserves: lump draw at month 0 of their funding phase.

    Combining draws with NCF (which already deducts non-BALANCE_ONLY uses as
    capital_outflow) yields: Δcumulative = BALANCE_ONLY_reserves + NOI - DS.
    """
    total = ZERO
    for ul in use_lines:
        label = getattr(ul, "label", "")
        amt = _to_decimal(getattr(ul, "amount", 0))
        if amt == ZERO:
            continue

        period_types = (
            (use_line_phase_overrides or {}).get(ul.id)
            or use_line_phase_map.get(
                str(getattr(ul, "phase", "") or "").replace("UseLinePhase.", ""),
                set(),
            )
        )
        if phase.period_type not in period_types:
            continue

        if label in balance_only_labels:
            # Reserves: inject as lump inflow at phase activation only
            if month_index == 0:
                total += amt
        else:
            # Regular uses: draw matches outflow timing
            timing = str(getattr(ul, "timing_type", "first_day")).replace("UseLineTiming.", "")
            if timing in ("spread", "spread_across_range"):
                n = max(phase.months, 1)
                monthly = _q(amt / Decimal(str(n)))
                if month_index == n - 1:
                    total += amt - _q(monthly * Decimal(str(n - 1)))
                else:
                    total += monthly
            else:
                # first_day / lump_sum: lump on month 0
                if month_index == 0:
                    total += amt

    return total


def _to_decimal(v: Any) -> Decimal:
    if v is None:
        return ZERO
    try:
        return Decimal(str(v))
    except Exception:
        return ZERO
