"""Unit tests for app/engines/dev_fee.py — auto Developer Fee recompute."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.dev_fee import recompute_auto_dev_fee
from app.models.deal import OperationalInputs, UseLine, UseLinePhase


def _ul(
    *,
    label: str,
    amount: Decimal,
    cost_category: str = "soft",
    phase: UseLinePhase = UseLinePhase.construction,
    is_auto_dev_fee: bool = False,
    dev_fee_pct: Decimal | None = None,
    dev_fee_basis: str | None = None,
) -> UseLine:
    return UseLine(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        label=label,
        phase=phase,
        amount=amount,
        timing_type="first_day",
        is_deferred=False,
        cost_category=cost_category,
        is_auto_dev_fee=is_auto_dev_fee,
        dev_fee_pct=dev_fee_pct,
        dev_fee_basis=dev_fee_basis,
    )


def _inputs(*, purchase_price: Decimal | None = None) -> OperationalInputs:
    return OperationalInputs(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        unit_count_new=8,
        purchase_price=purchase_price,
    )


@pytest.mark.unit
async def test_purchase_price_basis_uses_inputs_purchase_price(session):
    """5% × $1M purchase price = $50,000."""
    use_lines = [
        _ul(label="Acq", amount=Decimal("1000000"), cost_category="acquisition", phase=UseLinePhase.acquisition),
        _ul(
            label="Developer Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_basis="purchase_price",
        ),
    ]
    inputs = _inputs(purchase_price=Decimal("1000000"))

    await recompute_auto_dev_fee(use_lines, inputs, session)

    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert Decimal(str(auto.amount)) == Decimal("50000.00")


@pytest.mark.unit
async def test_purchase_price_basis_falls_back_to_acquisition_use_line(session):
    """When inputs.purchase_price is None, sum acquisition-phase Uses."""
    use_lines = [
        _ul(
            label="Acquisition",
            amount=Decimal("800000"),
            cost_category="acquisition",
            phase=UseLinePhase.acquisition,
        ),
        _ul(
            label="Developer Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_basis="purchase_price",
        ),
    ]
    inputs = _inputs(purchase_price=None)

    await recompute_auto_dev_fee(use_lines, inputs, session)

    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert Decimal(str(auto.amount)) == Decimal("40000.00")


@pytest.mark.unit
async def test_tpc_excl_self_basis_sums_other_use_lines(session):
    """12% × ($1M acq + $300k hard + $100k soft) = $168,000."""
    use_lines = [
        _ul(label="Acq", amount=Decimal("1000000"), cost_category="acquisition", phase=UseLinePhase.acquisition),
        _ul(label="Hard Costs", amount=Decimal("300000"), cost_category="hard"),
        _ul(label="Soft Costs", amount=Decimal("100000"), cost_category="soft"),
        _ul(
            label="Developer Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("12.0"),
            dev_fee_basis="tpc_excl_self",
        ),
    ]
    inputs = _inputs(purchase_price=Decimal("1000000"))

    await recompute_auto_dev_fee(use_lines, inputs, session)

    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert Decimal(str(auto.amount)) == Decimal("168000.00")


@pytest.mark.unit
async def test_tpc_basis_excludes_self_even_after_prior_compute(session):
    """If dev fee already has a non-zero amount, recompute must not double-count it."""
    use_lines = [
        _ul(label="Acq", amount=Decimal("1000000"), cost_category="acquisition", phase=UseLinePhase.acquisition),
        _ul(
            label="Developer Fee",
            amount=Decimal("999999"),  # stale value from prior pass
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("12.0"),
            dev_fee_basis="tpc_excl_self",
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(purchase_price=Decimal("1000000")), session)
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert Decimal(str(auto.amount)) == Decimal("120000.00")


@pytest.mark.unit
async def test_no_auto_dev_fee_row_is_no_op(session):
    """Engine must not crash when scenario has no auto Dev Fee Use Line."""
    use_lines = [
        _ul(label="Acq", amount=Decimal("1000000"), cost_category="acquisition", phase=UseLinePhase.acquisition),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(purchase_price=Decimal("1000000")), session)
    assert use_lines[0].amount == Decimal("1000000")


@pytest.mark.unit
async def test_zero_pct_disables_fee(session):
    """% = 0 collapses the auto Dev Fee amount to 0."""
    use_lines = [
        _ul(label="Acq", amount=Decimal("1000000"), cost_category="acquisition", phase=UseLinePhase.acquisition),
        _ul(
            label="Developer Fee",
            amount=Decimal("50000"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("0"),
            dev_fee_basis="tpc_excl_self",
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(purchase_price=Decimal("1000000")), session)
    auto = next(u for u in use_lines if u.is_auto_dev_fee)
    assert Decimal(str(auto.amount)) == Decimal("0.00")


@pytest.mark.unit
async def test_null_pct_is_no_op(session):
    """dev_fee_pct=None leaves amount untouched (defensive)."""
    use_lines = [
        _ul(
            label="Developer Fee",
            amount=Decimal("12345"),
            is_auto_dev_fee=True,
            dev_fee_pct=None,
            dev_fee_basis="tpc_excl_self",
        ),
    ]
    await recompute_auto_dev_fee(use_lines, _inputs(purchase_price=Decimal("0")), session)
    assert Decimal(str(use_lines[0].amount)) == Decimal("12345")


@pytest.mark.unit
async def test_purchase_price_zero_returns_zero_fee(session):
    """No purchase price + purchase_price basis → fee = 0, no crash."""
    use_lines = [
        _ul(
            label="Developer Fee",
            amount=Decimal("0"),
            is_auto_dev_fee=True,
            dev_fee_pct=Decimal("5.0"),
            dev_fee_basis="purchase_price",
        ),
    ]
    await recompute_auto_dev_fee(use_lines, None, session)
    assert Decimal(str(use_lines[0].amount)) == Decimal("0.00")
