"""Tests for the bank-account operating-proof extractor."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.engines.bank_account_extractor import (
    BankAccountInputs,
    extract_operating_proof_window,
)
from app.engines.bank_account import simulate


@dataclass
class _FakeRow:
    period: int
    period_type: str
    effective_gross_income: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    debt_service: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")


@dataclass
class _FakeUseLine:
    label: str
    amount: Decimal
    timing_type: str = "first_day"


def test_opening_cash_sums_first_day_reserves():
    use_lines = [
        _FakeUseLine("Operating Reserve",     Decimal("100_000")),
        _FakeUseLine("Interest Reserve",      Decimal("250_000")),
        _FakeUseLine("Lease-Up Reserve",      Decimal("150_000")),
        _FakeUseLine("Hard Costs",            Decimal("5_000_000")),  # not a reserve
        _FakeUseLine("Acquisition Cost",      Decimal("3_000_000")),  # not a reserve
    ]
    rows = [_FakeRow(period=0, period_type="lease_up")]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=0,
    )
    # OR + IR + LUR = 500K
    assert out.opening_cash == Decimal("500_000")


def test_reserves_with_non_first_day_timing_skipped():
    use_lines = [
        _FakeUseLine("Operating Reserve", Decimal("100_000"), timing_type="first_day"),
        _FakeUseLine("Operating Reserve", Decimal("999_999"), timing_type="monthly"),
    ]
    rows = [_FakeRow(period=0, period_type="lease_up")]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=0,
    )
    assert out.opening_cash == Decimal("100_000")


def test_rows_outside_window_excluded():
    rows = [
        _FakeRow(period=0, period_type="acquisition"),
        _FakeRow(period=12, period_type="construction"),
        _FakeRow(period=24, period_type="lease_up",  effective_gross_income=Decimal("10_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("3_000")),
        _FakeRow(period=25, period_type="lease_up",  effective_gross_income=Decimal("12_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("3_000")),
        _FakeRow(period=30, period_type="stabilized", effective_gross_income=Decimal("20_000"),
                 operating_expenses=Decimal("6_000"), debt_service=Decimal("3_000")),
    ]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=[],
        first_period_date=datetime(2026, 1, 1),
        co_period=24,
        stabilized_period=30,
    )
    # Only periods 24 and 25 fall in [24, 30) — lease-up rows
    assert len(out.months) == 2
    assert out.monthly_inflows[out.months[0]] == Decimal("10_000")
    assert out.monthly_outflows[out.months[0]] == Decimal("8_000")  # 5k + 3k
    assert out.monthly_inflows[out.months[1]] == Decimal("12_000")


def test_floor_set_to_operating_reserve_amount():
    rows = [
        _FakeRow(period=24, period_type="lease_up",  effective_gross_income=Decimal("10_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("3_000")),
    ]
    use_lines = [_FakeUseLine("Operating Reserve", Decimal("75_000"))]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=24,
    )
    assert out.monthly_floor[out.months[0]] == Decimal("75_000")


def test_explicit_or_amount_overrides_use_line():
    use_lines = [_FakeUseLine("Operating Reserve", Decimal("10_000"))]
    rows = [_FakeRow(period=0, period_type="lease_up",
                     effective_gross_income=Decimal("0"),
                     operating_expenses=Decimal("100"))]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=0,
        operating_reserve_amount=Decimal("250_000"),
    )
    assert out.monthly_floor[out.months[0]] == Decimal("250_000")
    # opening_cash unchanged — the explicit OR amount only overrides the floor
    assert out.opening_cash == Decimal("10_000")


def test_period_dates_walk_from_first_period_date():
    rows = [
        _FakeRow(period=10, period_type="lease_up"),
        _FakeRow(period=11, period_type="lease_up"),
        _FakeRow(period=12, period_type="lease_up"),
    ]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=[],
        first_period_date=datetime(2026, 1, 1),  # period 0 anchor
        co_period=10,
    )
    # period 10 = Nov 2026; period 11 = Dec 2026; period 12 = Jan 2027
    assert out.months == [
        datetime(2026, 11, 1),
        datetime(2026, 12, 1),
        datetime(2027, 1, 1),
    ]


def test_extractor_feeds_simulate_end_to_end():
    """
    End-to-end: build extractor inputs from a synthetic deal, hand off to
    simulate(), confirm the BankAccountReport matches expected balance walk.
    """
    rows = [
        _FakeRow(period=0, period_type="lease_up", effective_gross_income=Decimal("8_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("30_000")),
        _FakeRow(period=1, period_type="lease_up", effective_gross_income=Decimal("16_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("30_000")),
        _FakeRow(period=2, period_type="lease_up", effective_gross_income=Decimal("24_000"),
                 operating_expenses=Decimal("5_000"), debt_service=Decimal("30_000")),
    ]
    use_lines = [
        _FakeUseLine("Operating Reserve", Decimal("50_000")),
        _FakeUseLine("Lease-Up Reserve",  Decimal("30_000")),
    ]
    inputs = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=0,
    )
    report = simulate(
        months=inputs.months,
        opening_cash=inputs.opening_cash,
        monthly_inflows=inputs.monthly_inflows,
        monthly_outflows=inputs.monthly_outflows,
        monthly_floor=inputs.monthly_floor,
    )
    # Balance walk: 80K → 80K - 27K = 53K → 53K - 19K = 34K → 34K - 11K = 23K
    # Floor 50K throughout — months 2 and 3 violate
    assert report.opening_cash == Decimal("80_000")
    assert report.monthly[0].balance == Decimal("53_000")
    assert report.monthly[1].balance == Decimal("34_000")
    assert report.monthly[2].balance == Decimal("23_000")
    # max_shortfall = 50K - 23K = 27K — the gap the engine would close with
    # a Cash Flow Support Reserve at that amount
    assert report.max_shortfall == Decimal("27_000")
    assert not report.is_solvent
