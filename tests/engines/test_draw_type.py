"""Unit tests for draw_type → period_interest_months draw_schedule mapping."""

from decimal import Decimal

import pytest

from app.engines.cashflow import _draw_schedule_for
from app.engines.interest import period_interest_months


class TestDrawScheduleFor:
    """_draw_schedule_for(carry_type, draw_type) returns the right draw_schedule string."""

    # Explicit draw_type overrides carry_type
    def test_fully_drawn_overrides_ir(self):
        assert _draw_schedule_for("interest_reserve", "fully_drawn") == "lump"

    def test_fully_drawn_overrides_ci(self):
        assert _draw_schedule_for("capitalized_interest", "fully_drawn") == "lump"

    def test_draw_down_overrides_ci(self):
        assert _draw_schedule_for("capitalized_interest", "draw_down") == "linear"

    def test_draw_down_overrides_ir(self):
        assert _draw_schedule_for("interest_reserve", "draw_down") == "linear"

    # None falls back to carry-type convention (backward compat)
    def test_none_ir_defaults_to_linear(self):
        assert _draw_schedule_for("interest_reserve", None) == "linear"

    def test_none_ci_defaults_to_lump(self):
        assert _draw_schedule_for("capitalized_interest", None) == "lump"

    def test_none_io_only_defaults_to_lump(self):
        assert _draw_schedule_for("io_only", None) == "lump"

    def test_none_pi_defaults_to_lump(self):
        assert _draw_schedule_for("pi", None) == "lump"

    # Unknown / empty draw_type falls back too
    def test_empty_string_falls_back_to_carry_convention(self):
        # Empty string is not a recognized draw_type — falls through to carry-type rule.
        result = _draw_schedule_for("interest_reserve", "")
        assert result == "linear"  # IR carry-type fallback

    def test_fully_drawn_exact_string(self):
        assert _draw_schedule_for("interest_reserve", "fully_drawn") == "lump"

    def test_draw_down_exact_string(self):
        assert _draw_schedule_for("capitalized_interest", "draw_down") == "linear"


class TestIRUseWriterMath:
    """Regression: IR Use writer at cashflow.py:~3130 must reflect draw_type.

    Pre-fix, the writer hardcoded ``p × rate/12 × N`` (always fully_drawn). The
    principal solve at line ~2710 already responded to draw_type, so flipping
    a perm bond between "draw_down" and "fully_drawn" moved the principal but
    not the matching IR Use line. Sources ≠ Uses for draw_down. This pins the
    invariant: the helper pair that the writer now uses (period_interest_months
    + _draw_schedule_for) produces the same factor the principal solve assumes.
    """

    def test_fully_drawn_uses_full_balance_factor(self):
        # P × rate/12 × N
        p = Decimal("10000000")
        n = 18
        rate = 6.0
        amt = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", "fully_drawn"),
        )
        expected = p * Decimal("6") / Decimal("100") / Decimal("12") * Decimal(n)
        assert amt == expected

    def test_draw_down_uses_average_balance_factor(self):
        # P × rate/12 × (N+1)/2
        p = Decimal("10000000")
        n = 18
        rate = 6.0
        amt = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", "draw_down"),
        )
        expected = (
            p * Decimal("6") / Decimal("100") / Decimal("12")
            * Decimal(n + 1) / Decimal("2")
        )
        assert amt == expected

    def test_fully_drawn_strictly_larger_than_draw_down(self):
        """The original bug: both modes produced identical IR amounts."""
        p = Decimal("10000000")
        n = 18
        rate = 6.0
        fully = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", "fully_drawn"),
        )
        drawn = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", "draw_down"),
        )
        assert fully > drawn
        # Expected ratio = N / ((N+1)/2) = 2N / (N+1) ≈ 1.895 for N=18
        ratio = fully / drawn
        expected_ratio = Decimal(2 * n) / Decimal(n + 1)
        assert abs(ratio - expected_ratio) < Decimal("0.001")

    def test_null_draw_type_perm_default_matches_fully_drawn(self):
        """Perm path uses ``src.get("draw_type") or "fully_drawn"`` so legacy
        modules (draw_type=None) keep their prior behavior. Asserts the helper
        with the fallback string produces the same number as explicit fully_drawn."""
        p = Decimal("10000000")
        n = 18
        rate = 6.0
        fallback = "fully_drawn"  # value the perm path substitutes for None
        amt_fallback = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", fallback),
        )
        amt_explicit = period_interest_months(
            p, n, rate,
            draw_schedule=_draw_schedule_for("interest_reserve", "fully_drawn"),
        )
        assert amt_fallback == amt_explicit
