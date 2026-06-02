"""Deferred Developer Fee balance schedule unit tests.

Covers ``compute_deferred_balance_schedule`` from
``app/engines/dev_fee_balance.py``: the Phase B float-earnings
deferred-balance consumer used by the CF waterfall.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engines.dev_fee_balance import (
    DeferredBalanceResult,
    DeferredBalanceRow,
    compute_deferred_balance_schedule,
    float_topups_by_milestone,
    serialize_balance_result,
)


ZERO = Decimal("0")


@pytest.mark.unit
def test_zero_deferred_returns_empty_result():
    r = compute_deferred_balance_schedule(
        deferred_at_close=ZERO,
        period_count=12,
    )
    assert r.opening_at_close == ZERO
    assert r.rows == tuple()
    assert r.fully_paid_period is None


@pytest.mark.unit
def test_zero_period_count_returns_empty_result():
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("100000"),
        period_count=0,
    )
    assert r.rows == tuple()
    assert r.fully_paid_period is None


@pytest.mark.unit
def test_no_paydowns_balance_flat_across_horizon():
    """Without any paydowns, balance never decreases and remains == opening."""
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("500000"),
        period_count=24,
    )
    assert len(r.rows) == 24
    assert all(row.opening_balance == Decimal("500000.000000") for row in r.rows)
    assert all(row.closing_balance == Decimal("500000.000000") for row in r.rows)
    assert all(row.paydown_total == ZERO for row in r.rows)
    assert r.fully_paid_period is None
    assert r.remaining_at_horizon() == Decimal("500000.000000")


@pytest.mark.unit
def test_waterfall_paydown_drains_balance_to_zero_at_expected_period():
    """100k/month paydown drains 500k balance in 5 periods."""
    paydowns = {p: Decimal("100000") for p in range(1, 10)}
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("500000"),
        period_count=10,
        waterfall_paydowns_by_period=paydowns,
    )
    assert r.fully_paid_period == 5
    # Periods 1–5 each pay 100k; periods 6–10 see balance=0, paydown=0.
    for p in range(1, 6):
        assert r.rows[p - 1].paydown_from_waterfall == Decimal("100000.000000")
        assert r.rows[p - 1].closing_balance == Decimal(str((5 - p) * 100000)).quantize(Decimal("0.000001"))
    for p in range(6, 11):
        assert r.rows[p - 1].paydown_from_waterfall == ZERO
        assert r.rows[p - 1].closing_balance == ZERO


@pytest.mark.unit
def test_waterfall_paydown_capped_at_running_balance_not_negative():
    """Even if the waterfall hands the balance more than it owes, closing >= 0."""
    paydowns = {1: Decimal("999999999")}
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("12345"),
        period_count=3,
        waterfall_paydowns_by_period=paydowns,
    )
    assert r.rows[0].paydown_from_waterfall == Decimal("12345.000000")
    assert r.rows[0].closing_balance == ZERO
    assert r.fully_paid_period == 1
    # Remaining periods do nothing.
    assert r.rows[1].opening_balance == ZERO
    assert r.rows[2].opening_balance == ZERO


@pytest.mark.unit
def test_float_topup_drains_balance_at_a_single_milestone_period():
    """A one-shot float topup at period 6 drains the entire remaining balance."""
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("250000"),
        period_count=12,
        float_topups_by_period={6: Decimal("300000")},  # bigger than balance
    )
    assert r.fully_paid_period == 6
    assert r.rows[5].paydown_from_float_topup == Decimal("250000.000000")
    # Float topup is capped at the opening balance.
    assert r.rows[5].closing_balance == ZERO


@pytest.mark.unit
def test_float_topup_takes_priority_over_waterfall_in_same_period():
    """When both arrive in the same period, float topup applies first."""
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("100000"),
        period_count=2,
        waterfall_paydowns_by_period={1: Decimal("60000")},
        float_topups_by_period={1: Decimal("80000")},
    )
    # Float topup gets 80k of room; waterfall finishes the remaining 20k.
    assert r.rows[0].paydown_from_float_topup == Decimal("80000.000000")
    assert r.rows[0].paydown_from_waterfall == Decimal("20000.000000")
    assert r.rows[0].closing_balance == ZERO
    assert r.fully_paid_period == 1


@pytest.mark.unit
def test_invariants_opening_equals_prior_closing():
    """For every period N>1, opening_balance == prior closing_balance."""
    paydowns = {2: Decimal("50000"), 5: Decimal("25000")}
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("200000"),
        period_count=8,
        waterfall_paydowns_by_period=paydowns,
    )
    for i in range(1, len(r.rows)):
        assert r.rows[i].opening_balance == r.rows[i - 1].closing_balance


@pytest.mark.unit
def test_serialize_balance_result_round_trip_shape():
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("100"),
        period_count=2,
        waterfall_paydowns_by_period={1: Decimal("40"), 2: Decimal("60")},
    )
    d = serialize_balance_result(r)
    assert d["opening_at_close"] == "100.000000"
    assert d["fully_paid_period"] == 2
    assert d["total_paid"] == "100.000000"
    assert d["remaining_at_horizon"] == "0.000000"
    assert len(d["periods"]) == 2
    assert d["periods"][0]["paydown_from_waterfall"] == "40.000000"
    assert d["periods"][1]["paydown_from_waterfall"] == "60.000000"


@pytest.mark.unit
def test_float_topups_by_milestone_aggregates_by_period_via_lookup():
    """Multiple float sources hitting the same period sum together."""
    import uuid as _uuid

    class _Fake:
        def __init__(self, ms_id, amt):
            self.paydown_milestone_id = ms_id
            self.dev_fee_topup_amount = amt

    ms_a, ms_b, ms_orphan = _uuid.uuid4(), _uuid.uuid4(), _uuid.uuid4()
    lookup = {ms_a: 3, ms_b: 3}  # ms_orphan deliberately missing
    out = float_topups_by_milestone(
        float_results=[
            _Fake(ms_a, Decimal("10")),
            _Fake(ms_b, Decimal("15")),
            _Fake(ms_orphan, Decimal("999")),  # silently dropped (warning surfaced upstream)
            _Fake(None, Decimal("100")),       # no milestone → dropped
            _Fake(ms_a, ZERO),                 # zero amount → no entry
        ],
        milestone_to_period=lookup,
    )
    assert out == {3: Decimal("25")}


@pytest.mark.unit
def test_dataclass_paydown_total_property():
    row = DeferredBalanceRow(
        period=1,
        opening_balance=Decimal("100"),
        paydown_from_waterfall=Decimal("30"),
        paydown_from_float_topup=Decimal("40"),
        closing_balance=Decimal("30"),
    )
    assert row.paydown_total == Decimal("70")


@pytest.mark.unit
def test_result_total_paid_sums_across_all_rows():
    r = compute_deferred_balance_schedule(
        deferred_at_close=Decimal("90"),
        period_count=3,
        waterfall_paydowns_by_period={1: Decimal("30"), 2: Decimal("30"), 3: Decimal("30")},
    )
    assert r.total_paid() == Decimal("90.000000")
    assert isinstance(r, DeferredBalanceResult)
