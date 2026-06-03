"""Tests for app/engines/loan_balance.py — the two-balance-track scaffold.

Locks the spec convention: interest-bearing balance is held flat at the
original principal; only the payoff balance reduces on paydowns / sweeps.
Slice 5's lease-up sweep will route excess LUR through this helper to
guarantee interest invariance to the sweep.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.debt_paydown import PaydownEvent
from app.engines.loan_balance import (
    LoanBalanceTracker,
    build_trackers,
    record_paydowns_for_trackers,
)


def _event(module_id: uuid.UUID, amount: str, *, milestone_id: uuid.UUID | None = None,
           label: str = "Test") -> PaydownEvent:
    return PaydownEvent(
        debt_module_id=module_id,
        milestone_id=milestone_id or uuid.uuid4(),
        amount=Decimal(amount),
        label=label,
    )


@pytest.mark.unit
def test_no_paydowns_both_tracks_equal_principal():
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("10000000"))

    assert t.interest_bearing_balance() == Decimal("10000000")
    # Pass the un-amortized principal as the balloon — IO-style loan.
    assert t.payoff_balance_at(months_elapsed=24, balloon_from_amortization=Decimal("10000000")) == Decimal("10000000.000000")


@pytest.mark.unit
def test_paydown_reduces_payoff_only_not_interest_bearing():
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("10000000"))

    t.record_paydown(_event(mid, "1500000"))

    assert t.interest_bearing_balance() == Decimal("10000000")  # unchanged
    assert t.payoff_balance_at(
        months_elapsed=24, balloon_from_amortization=Decimal("10000000")
    ) == Decimal("8500000.000000")


@pytest.mark.unit
def test_cumulative_paydowns_sums_correctly():
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("10000000"))

    t.record_paydown(_event(mid, "300000"))
    t.record_paydown(_event(mid, "450000"))
    t.record_paydown(_event(mid, "125000"))

    assert t.cumulative_paydowns() == Decimal("875000.000000")
    assert t.interest_bearing_balance() == Decimal("10000000")


@pytest.mark.unit
def test_zero_or_negative_amount_paydown_ignored():
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("5000000"))

    t.record_paydown(_event(mid, "0"))
    t.record_paydown(_event(mid, "-100"))
    t.record_paydown(_event(mid, "1000"))

    assert t.cumulative_paydowns() == Decimal("1000.000000")


@pytest.mark.unit
def test_payoff_balance_clamps_at_zero():
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("1000000"))

    t.record_paydown(_event(mid, "2000000"))  # more than balloon

    # Balloon at this point is amortized to 800000; subtract paydowns; clamp ≥0.
    assert t.payoff_balance_at(
        months_elapsed=12, balloon_from_amortization=Decimal("800000")
    ) == Decimal("0.000000")


@pytest.mark.unit
def test_paydown_targeting_wrong_module_raises():
    own = uuid.uuid4()
    other = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=own, original_principal=Decimal("1000000"))

    with pytest.raises(ValueError, match="Paydown event targets"):
        t.record_paydown(_event(other, "1000"))


@pytest.mark.unit
def test_build_trackers_from_principals_dict():
    a, b = uuid.uuid4(), uuid.uuid4()
    trackers = build_trackers(
        debt_module_principals={a: Decimal("5000000"), b: Decimal("7500000")}
    )

    assert trackers[a].original_principal == Decimal("5000000.000000")
    assert trackers[b].original_principal == Decimal("7500000.000000")
    assert trackers[a].cumulative_paydowns() == Decimal("0")


@pytest.mark.unit
def test_record_paydowns_for_trackers_fans_to_correct_module():
    a, b = uuid.uuid4(), uuid.uuid4()
    unknown = uuid.uuid4()
    trackers = build_trackers(
        debt_module_principals={a: Decimal("5000000"), b: Decimal("7500000")}
    )

    events = [
        _event(a, "100000"),
        _event(b, "250000"),
        _event(a, "50000"),
        _event(unknown, "999999"),  # dropped silently
    ]
    record_paydowns_for_trackers(trackers=trackers, events=events)

    assert trackers[a].cumulative_paydowns() == Decimal("150000.000000")
    assert trackers[b].cumulative_paydowns() == Decimal("250000.000000")


@pytest.mark.unit
def test_balloon_passthrough_lets_callers_keep_existing_amort_math():
    """Tracker is decoupled from amortization; caller supplies the balloon.

    Lets cashflow.py keep computing balloons via `_balloon_balance` while
    still gaining the two-track separation — no engine math moves.
    """
    mid = uuid.uuid4()
    t = LoanBalanceTracker(debt_module_id=mid, original_principal=Decimal("10000000"))

    # Caller passes a balloon at month 18 (amortized down from $10M to $9.2M),
    # plus $400k of accumulated sweeps.
    t.record_paydown(_event(mid, "400000"))
    assert t.payoff_balance_at(
        months_elapsed=18, balloon_from_amortization=Decimal("9200000")
    ) == Decimal("8800000.000000")

    # Interest accrual would still be on the full $10M.
    assert t.interest_bearing_balance() == Decimal("10000000")
