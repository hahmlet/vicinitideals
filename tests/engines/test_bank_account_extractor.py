"""Tests for the bank-account operating-proof extractor."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.engines.bank_account_extractor import (
    BankAccountInputs,
    extract_full_window_proof,
    extract_operating_proof_window,
)
from app.engines.bank_account import simulate


@dataclass
class _FakeMonthly:
    """Mirror of draw_schedule.MonthlyCashFlow for full-window tests."""
    date: datetime
    draw_received: Decimal = Decimal("0")
    uses_paid: Decimal = Decimal("0")
    interest_paid: Decimal = Decimal("0")


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


def test_cash_flow_support_reserve_counts_toward_opening_cash():
    """Convergence requirement: the auto-emitted "Cash Flow Support Reserve"
    UseLine must feed opening_cash, otherwise the iteration loop spins at
    the same shortfall forever and never converges. Engine emits the
    reserve on iteration N → extractor must include it on iteration N+1.
    """
    use_lines = [
        _FakeUseLine("Operating Reserve",        Decimal("100_000")),
        _FakeUseLine("Cash Flow Support Reserve", Decimal("60_000")),
    ]
    rows = [_FakeRow(period=0, period_type="lease_up")]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=0,
    )
    # OR + CFS = 160K. Without CFS feeding opening_cash, iteration loop
    # would never close the shortfall the CFS was sized to plug.
    assert out.opening_cash == Decimal("160_000")


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


# ---------------------------------------------------------------------------
# extract_full_window_proof — Day 0 → Stabilization Start
# ---------------------------------------------------------------------------


def test_full_window_construction_plus_leaseup_concatenates_chronologically():
    """Both segments build one contiguous month-aligned timeline."""
    construction = [
        _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("500_000"),
                     uses_paid=Decimal("400_000"), interest_paid=Decimal("5_000")),
        _FakeMonthly(date=datetime(2026, 2, 1), draw_received=Decimal("600_000"),
                     uses_paid=Decimal("550_000"), interest_paid=Decimal("8_000")),
    ]
    rows = [
        _FakeRow(period=2, period_type="lease_up", effective_gross_income=Decimal("10_000"),
                 operating_expenses=Decimal("4_000"), debt_service=Decimal("3_000")),
        _FakeRow(period=3, period_type="lease_up", effective_gross_income=Decimal("20_000"),
                 operating_expenses=Decimal("4_000"), debt_service=Decimal("3_000")),
    ]
    out = extract_full_window_proof(
        construction_monthly=construction,
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("60_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=4,
    )
    # 4 months total: 2 construction + 2 lease-up
    assert len(out.months) == 4
    assert out.months[0] == datetime(2026, 1, 1)
    assert out.months[1] == datetime(2026, 2, 1)
    assert out.months[2] == datetime(2026, 3, 1)
    assert out.months[3] == datetime(2026, 4, 1)
    # Construction-month flows
    assert out.monthly_inflows[out.months[0]] == Decimal("500_000")
    assert out.monthly_outflows[out.months[0]] == Decimal("405_000")  # 400K + 5K
    # Lease-up-month flows
    assert out.monthly_inflows[out.months[2]] == Decimal("10_000")
    assert out.monthly_outflows[out.months[2]] == Decimal("7_000")  # 4K + 3K
    # Floor uniform across all months
    assert all(out.monthly_floor[m] == Decimal("60_000") for m in out.months)


def test_full_window_construction_only_when_no_leaseup_rows():
    """If cash_flow_rows is empty inside the window, construction-only output is built."""
    construction = [
        _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("100_000"),
                     uses_paid=Decimal("90_000")),
    ]
    out = extract_full_window_proof(
        construction_monthly=construction,
        cash_flow_rows=[],
        use_lines=[],
        first_period_date=datetime(2026, 1, 1),
        co_period=1,
        stabilized_period=2,
    )
    assert len(out.months) == 1
    assert out.monthly_inflows[out.months[0]] == Decimal("100_000")


def test_full_window_overlap_construction_wins():
    """If a construction date and a lease-up row land on the same month, construction wins."""
    construction = [
        _FakeMonthly(date=datetime(2026, 3, 1), draw_received=Decimal("999_999"),
                     uses_paid=Decimal("0")),
    ]
    rows = [
        # Period 2 from 2026-01-01 anchor = March 2026 — collides with construction
        _FakeRow(period=2, period_type="lease_up", effective_gross_income=Decimal("123"),
                 operating_expenses=Decimal("456"), debt_service=Decimal("0")),
    ]
    out = extract_full_window_proof(
        construction_monthly=construction,
        cash_flow_rows=rows,
        use_lines=[],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=3,
    )
    assert len(out.months) == 1
    # Construction values survive — lease-up row was dropped
    assert out.monthly_inflows[out.months[0]] == Decimal("999_999")
    assert out.monthly_outflows[out.months[0]] == Decimal("0")


def test_full_window_opening_cash_matches_reserves():
    """Same opening_cash rule as the operating-only extractor."""
    use_lines = [
        _FakeUseLine("Operating Reserve", Decimal("100_000")),
        _FakeUseLine("Lease-Up Reserve",  Decimal("50_000")),
        _FakeUseLine("Hard Costs",        Decimal("5_000_000")),
    ]
    out = extract_full_window_proof(
        construction_monthly=[
            _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("0"))
        ],
        cash_flow_rows=[],
        use_lines=use_lines,
        first_period_date=datetime(2026, 1, 1),
        co_period=1,
        stabilized_period=2,
    )
    assert out.opening_cash == Decimal("150_000")


def test_full_window_explicit_or_amount_overrides_floor():
    out = extract_full_window_proof(
        construction_monthly=[
            _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("0"))
        ],
        cash_flow_rows=[],
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=1,
        stabilized_period=2,
        operating_reserve_amount=Decimal("250_000"),
    )
    assert out.monthly_floor[out.months[0]] == Decimal("250_000")


def test_full_window_feeds_simulate_end_to_end():
    """End-to-end: full-window inputs flow through simulate() solvent."""
    # 2 construction months: draws cover uses + interest exactly; balance stays
    # at opening_cash (50K).
    construction = [
        _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("100_000"),
                     uses_paid=Decimal("100_000"), interest_paid=Decimal("0")),
        _FakeMonthly(date=datetime(2026, 2, 1), draw_received=Decimal("100_000"),
                     uses_paid=Decimal("100_000"), interest_paid=Decimal("0")),
    ]
    # 2 lease-up months: NOI positive (income > opex + DS).
    rows = [
        _FakeRow(period=2, period_type="lease_up",
                 effective_gross_income=Decimal("60_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
        _FakeRow(period=3, period_type="lease_up",
                 effective_gross_income=Decimal("80_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
    ]
    inputs = extract_full_window_proof(
        construction_monthly=construction,
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=4,
    )
    report = simulate(
        months=inputs.months,
        opening_cash=inputs.opening_cash,
        monthly_inflows=inputs.monthly_inflows,
        monthly_outflows=inputs.monthly_outflows,
        monthly_floor=inputs.monthly_floor,
    )
    # Balance walk:
    #   open=50K → c1 +0 = 50K → c2 +0 = 50K → l1 +10K = 60K → l2 +30K = 90K
    assert report.opening_cash == Decimal("50_000")
    assert report.monthly[0].balance == Decimal("50_000")
    assert report.monthly[1].balance == Decimal("50_000")
    assert report.monthly[2].balance == Decimal("60_000")
    assert report.monthly[3].balance == Decimal("90_000")
    assert report.is_solvent
    assert report.max_shortfall == Decimal("0")


# ---------------------------------------------------------------------------
# dev_fee_paydowns_by_period — deferred Dev Fee outflows from waterfall
# ---------------------------------------------------------------------------


def test_dev_fee_paydowns_added_to_outflows_in_operating_window():
    """Waterfall-driven deferred Dev Fee paydowns must show up as outflows so
    the proof's CFS sizing accounts for cash leaving the operating account."""
    rows = [
        _FakeRow(period=2, period_type="lease_up",
                 effective_gross_income=Decimal("60_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
        _FakeRow(period=3, period_type="lease_up",
                 effective_gross_income=Decimal("80_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
    ]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=4,
        dev_fee_paydowns_by_period={2: Decimal("10_000"), 3: Decimal("25_000")},
    )
    m2, m3 = out.months[0], out.months[1]
    assert out.monthly_outflows[m2] == Decimal("60_000")  # 20K opex + 30K DS + 10K paydown
    assert out.monthly_outflows[m3] == Decimal("75_000")  # 20K opex + 30K DS + 25K paydown


def test_dev_fee_paydowns_none_is_noop_in_operating_window():
    """Defaulting paydowns to None must preserve legacy outflow math."""
    rows = [
        _FakeRow(period=2, period_type="lease_up",
                 effective_gross_income=Decimal("60_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
    ]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=3,
    )
    assert out.monthly_outflows[out.months[0]] == Decimal("50_000")


def test_dev_fee_paydowns_added_to_outflows_in_full_window():
    """Lease-up segment of full window picks up paydowns; construction segment
    is unaffected (deferred Dev Fee paydowns only fire post-CO)."""
    construction = [
        _FakeMonthly(date=datetime(2026, 1, 1), draw_received=Decimal("100_000"),
                     uses_paid=Decimal("100_000"), interest_paid=Decimal("0")),
    ]
    rows = [
        _FakeRow(period=1, period_type="lease_up",
                 effective_gross_income=Decimal("60_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
        _FakeRow(period=2, period_type="lease_up",
                 effective_gross_income=Decimal("80_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
    ]
    out = extract_full_window_proof(
        construction_monthly=construction,
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=1,
        stabilized_period=3,
        dev_fee_paydowns_by_period={1: Decimal("15_000"), 2: Decimal("40_000")},
    )
    # Construction month outflow unchanged (paydown for period 1 only hits the
    # lease-up row — construction segment owns period 0 here by calendar date).
    m_c = out.months[0]
    assert out.monthly_outflows[m_c] == Decimal("100_000")  # uses + interest, no paydown
    # Lease-up months get paydowns folded into outflows.
    m_l1 = out.months[1]
    m_l2 = out.months[2]
    assert out.monthly_outflows[m_l1] == Decimal("65_000")  # 20K opex + 30K DS + 15K paydown
    assert out.monthly_outflows[m_l2] == Decimal("90_000")  # 20K opex + 30K DS + 40K paydown


def test_dev_fee_paydown_for_unmatched_period_is_ignored():
    """A paydown entry whose period falls outside the proof window must not
    leak into outflows or shift the timeline."""
    rows = [
        _FakeRow(period=2, period_type="lease_up",
                 effective_gross_income=Decimal("60_000"),
                 operating_expenses=Decimal("20_000"), debt_service=Decimal("30_000")),
    ]
    out = extract_operating_proof_window(
        cash_flow_rows=rows,
        use_lines=[_FakeUseLine("Operating Reserve", Decimal("50_000"))],
        first_period_date=datetime(2026, 1, 1),
        co_period=2,
        stabilized_period=3,
        dev_fee_paydowns_by_period={99: Decimal("12_345")},  # period not in window
    )
    assert out.monthly_outflows[out.months[0]] == Decimal("50_000")
