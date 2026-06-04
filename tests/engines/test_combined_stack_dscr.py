"""Combined-stack DSCR: auto-sized debt must be sized off NOI net of
fixed (non-auto-sized) debt service.

Regression: a deal with a fixed senior assumable loan ($12.5M @ 3.12%,
30y amort, ~$643k/yr P&I) plus an auto-sized RJ Bond at 6% was sizing
the bond off the full NOI ($1.47M), ignoring the assumable's claim.
Combined-stack DSCR fell to 0.49 while staging dscr_min said 1.15.

Fix: `_sum_fixed_debt_ds_annual()` computes fixed-debt service before
the auto-sizing loop; the loop subtracts it from NOI before solving
`p_dscr`. When fixed DS ≥ NOI/DSCR target, auto debt sizes to zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest

from app.engines.cashflow import _monthly_pmt, _sum_fixed_debt_ds_annual


@dataclass
class _Module:
    vehicle_type: str = "debt"
    source: dict = field(default_factory=dict)
    carry: dict = field(default_factory=dict)
    # _is_debt_cm reads `vehicle_type` only.

    # Some engine paths consult these attrs; defaults keep them inert.
    active_phase_start: str | None = None
    active_phase_end: str | None = None


@pytest.mark.unit
def test_empty_stack_returns_zero() -> None:
    assert _sum_fixed_debt_ds_annual([]) == Decimal("0")


@pytest.mark.unit
def test_only_auto_debt_returns_zero() -> None:
    """Auto-sized debt is what we are sizing — must NOT subtract itself."""
    auto = _Module(
        source={"amount": "10000000", "interest_rate_pct": 6.0, "auto_size": True}
    )
    assert _sum_fixed_debt_ds_annual([auto]) == Decimal("0")


@pytest.mark.unit
def test_fixed_debt_with_no_rate_skipped() -> None:
    """Owner loan / soft loan with no rate has no DS to subtract."""
    soft = _Module(source={"amount": "500000"})
    assert _sum_fixed_debt_ds_annual([soft]) == Decimal("0")


@pytest.mark.unit
def test_fixed_debt_zero_amount_skipped() -> None:
    placeholder = _Module(source={"amount": "0", "interest_rate_pct": 6.0})
    assert _sum_fixed_debt_ds_annual([placeholder]) == Decimal("0")


@pytest.mark.unit
def test_equity_module_skipped() -> None:
    equity = _Module(
        vehicle_type="equity",
        source={"amount": "5000000", "interest_rate_pct": 8.0},
    )
    assert _sum_fixed_debt_ds_annual([equity]) == Decimal("0")


@pytest.mark.unit
def test_fixed_debt_ds_matches_amortization_formula() -> None:
    """$12.545M @ 3.12% / 30y → annual P&I ~= $643,832."""
    assumable = _Module(
        source={
            "amount": "12545000",
            "interest_rate_pct": 3.12,
            "amort_term_years": 30,
        }
    )
    got = _sum_fixed_debt_ds_annual([assumable])
    expected = _monthly_pmt(Decimal("12545000"), 3.12, 30) * Decimal("12")
    assert got == expected
    # Sanity-check the magnitude so a future formula change is flagged.
    assert Decimal("640000") < got < Decimal("647000")


@pytest.mark.unit
def test_fixed_plus_auto_only_subtracts_fixed() -> None:
    """Real-world repro: one fixed assumable + one auto bond."""
    fixed = _Module(
        source={
            "amount": "12545000",
            "interest_rate_pct": 3.12,
            "amort_term_years": 30,
        }
    )
    auto = _Module(
        source={
            "amount": "14000000",
            "interest_rate_pct": 6.0,
            "amort_term_years": 30,
            "auto_size": True,
        }
    )
    got = _sum_fixed_debt_ds_annual([fixed, auto])
    fixed_only = _sum_fixed_debt_ds_annual([fixed])
    assert got == fixed_only


@pytest.mark.unit
def test_multiple_fixed_debts_summed() -> None:
    a = _Module(
        source={"amount": "5000000", "interest_rate_pct": 4.0, "amort_term_years": 25}
    )
    b = _Module(
        source={"amount": "3000000", "interest_rate_pct": 5.5, "amort_term_years": 20}
    )
    expected = (
        _monthly_pmt(Decimal("5000000"), 4.0, 25) * Decimal("12")
        + _monthly_pmt(Decimal("3000000"), 5.5, 20) * Decimal("12")
    )
    assert _sum_fixed_debt_ds_annual([a, b]) == expected
