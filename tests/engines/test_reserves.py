"""Tests for the reserves-spec-align engine changes.

Locks the spec contracts introduced in Slice 3 of the plan:
* Interest Reserve sizing is **LUR-blind**: the ramping lease-up revenue
  does NOT offset sized interest. The lender's full interest is funded at
  Close; ramping rent becomes a principal-paydown sweep at runtime
  (Slice 5).
* The default draw-schedule for IR carry is ``"lump"`` (full funded balance
  from Close), not the legacy ``"linear"`` (N+1/2 average draw).
* The Operating Reserve basis is parametrized on
  ``OperationalInputs.operation_reserve_basis`` ∈ {ds, opex, opex_plus_ds},
  defaulting to ``"ds"``.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.engines.cashflow import _draw_schedule_for, _ir_lease_up_pool


@pytest.mark.unit
def test_ir_lease_up_pool_lur_blind_with_zero_revenue():
    """Baseline: no revenue, no opex, just interest on the funded balance."""
    pool = _ir_lease_up_pool(
        funded=Decimal("10000000"),
        rate_pct=Decimal("6"),
        n_months=12,
        lease_up_phase=None,
        streams=[],
        expense_lines=[],
        inputs=None,
    )
    # $10M × 6% / 12 = $50,000 / mo × 12 mo = $600,000
    assert pool == Decimal("600000.000000")


@pytest.mark.unit
def test_ir_lease_up_pool_lur_blind_ignores_revenue_curve():
    """Spec §3.1 — revenue passed through any curve must NOT shrink IR.

    Whether the user supplies a flat curve, a ramp, or an empty list, the
    IR pool depends only on funded × rate × months. This is the lever the
    review identified as the biggest misalignment.
    """
    funded = Decimal("10000000")
    rate = Decimal("6")
    n = 12

    # Fabricate stream/expense objects that, under the legacy LUR-aware
    # logic, would have netted ~$300k+ of revenue against interest.
    fake_lease_up_phase = SimpleNamespace(months=n)
    fake_stream = SimpleNamespace(
        amount_per_unit_monthly=Decimal("3000"),
        unit_count=20,
        initial_occupancy_pct=Decimal("0"),
        stabilized_occupancy_pct=Decimal("95"),
        bad_debt_pct=Decimal("0"),
        concessions_pct=Decimal("0"),
        active_in_phases=["lease_up", "stabilized"],
    )
    fake_expense = SimpleNamespace(
        annual_amount=Decimal("120000"),
        active_in_phases=["lease_up", "stabilized"],
    )

    blind = _ir_lease_up_pool(
        funded=funded,
        rate_pct=rate,
        n_months=n,
        lease_up_phase=fake_lease_up_phase,
        streams=[fake_stream],
        expense_lines=[fake_expense],
        inputs=SimpleNamespace(),
    )
    zero_rev = _ir_lease_up_pool(
        funded=funded,
        rate_pct=rate,
        n_months=n,
        lease_up_phase=None,
        streams=[],
        expense_lines=[],
        inputs=None,
    )
    # Critical invariant: revenue inputs cannot move the IR pool.
    assert blind == zero_rev == Decimal("600000.000000")


@pytest.mark.unit
def test_ir_lease_up_pool_zero_when_no_months_or_zero_rate():
    assert _ir_lease_up_pool(
        funded=Decimal("1000000"),
        rate_pct=Decimal("6"),
        n_months=0,
        lease_up_phase=None,
        streams=[],
        expense_lines=[],
        inputs=None,
    ) == Decimal("0")
    assert _ir_lease_up_pool(
        funded=Decimal("1000000"),
        rate_pct=Decimal("0"),
        n_months=12,
        lease_up_phase=None,
        streams=[],
        expense_lines=[],
        inputs=None,
    ) == Decimal("0")


@pytest.mark.unit
def test_default_draw_schedule_is_lump():
    """Spec §2 — interest accrues on the full funded balance from Close.

    The legacy ``"linear"`` default for interest_reserve carry assumed an
    average-draw N+1/2 factor that understated the reserve. Default is now
    ``"lump"`` for both carry types.
    """
    assert _draw_schedule_for("interest_reserve", None) == "lump"
    assert _draw_schedule_for("capitalized_interest", None) == "lump"
    # io_only / pi don't go through this helper for sizing but should still
    # behave sensibly.
    assert _draw_schedule_for("io_only", None) == "lump"


@pytest.mark.unit
def test_explicit_draw_type_overrides_lump_default():
    """``draw_type`` field on source still wins.

    Construction loans drawn down month-by-month set ``draw_type="draw_down"``
    on the source and continue to size at the (N+1)/2 average factor.
    """
    assert _draw_schedule_for("interest_reserve", "draw_down") == "linear"
    assert _draw_schedule_for("interest_reserve", "fully_drawn") == "lump"
    assert _draw_schedule_for("capitalized_interest", "draw_down") == "linear"


@pytest.mark.unit
def test_ir_lease_up_pool_signature_kept_for_call_site_compat():
    """The helper must still accept the legacy positional arguments so
    existing call sites do not break. Slice 5 will sweep through and
    drop the unused params; for now they stay in the signature."""
    # Should not raise.
    _ir_lease_up_pool(
        funded=Decimal("5000000"),
        rate_pct=6.0,                       # float, not Decimal
        n_months=6,
        lease_up_phase=None,
        streams=[],
        expense_lines=[],
        inputs=None,
    )
