"""Unit tests for draw_type → period_interest_months draw_schedule mapping."""

import pytest

from app.engines.cashflow import _draw_schedule_for


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
