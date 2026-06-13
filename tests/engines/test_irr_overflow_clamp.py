"""Regression: waterfall IRR must never overflow the party_irr_pct column.

Production bug (observed): a degenerate cash-flow series (near-zero equity vs
a huge distribution) made pyxirr return an astronomically large IRR
(~1.3e12 %). party_irr_pct is NUMERIC(18, 6) — values must round to abs
< 10^12 — so the bulk INSERT INTO waterfall_results failed with
``asyncpg.exceptions.NumericValueOutOfRangeError`` and 500'd the whole
compute.

Fix: ``_compute_xirr_pct`` drops non-finite and astronomically large IRRs to
None instead of returning a value that overflows the column.

Run:
    uv run pytest tests/engines/test_irr_overflow_clamp.py -m unit -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engines.waterfall import _IRR_PCT_LIMIT, _compute_xirr_pct


@pytest.mark.unit
def test_normal_irr_returns_finite_value() -> None:
    """A sane series still produces a real IRR — the clamp must not over-fire."""
    # -$1.0M at month 0, +$1.2M at month 12 → ~20%/yr.
    pct = _compute_xirr_pct({0: Decimal("-1000000"), 12: Decimal("1200000")})
    assert pct is not None
    assert Decimal("10") < pct < Decimal("30")


@pytest.mark.unit
def test_large_but_in_range_irr_not_clamped() -> None:
    """A high-but-real IRR (a few hundred %) is below the limit → kept."""
    # -$1k at month 0, +$6k at month 12 → ~500%/yr.
    pct = _compute_xirr_pct({0: Decimal("-1000"), 12: Decimal("6000")})
    assert pct is not None
    assert pct < _IRR_PCT_LIMIT


@pytest.mark.unit
def test_degenerate_huge_irr_clamped_to_none() -> None:
    """Near-zero outflow vs a giant inflow → IRR explodes past the column
    limit. Must clamp to None rather than return a value that overflows
    NUMERIC(18, 6) and 500s the compute."""
    pct = _compute_xirr_pct({0: Decimal("-100"), 12: Decimal("100000000000000")})
    assert pct is None


@pytest.mark.unit
def test_all_positive_series_returns_none() -> None:
    """No sign change → no IRR (and certainly no overflow)."""
    assert _compute_xirr_pct({0: Decimal("1000"), 12: Decimal("2000")}) is None


@pytest.mark.unit
def test_empty_series_returns_none() -> None:
    assert _compute_xirr_pct({}) is None
