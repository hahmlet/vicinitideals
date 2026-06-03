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

from app.engines.cashflow import _draw_schedule_for, _ir_lease_up_pool, _odr_pool
from app.engines.dev_fee import BASIS_BUCKET_KEYS, classify_basis_bucket
from app.models.deal import IncomeStream, OperationalInputs, OperatingExpenseLine, UseLine

ZERO = Decimal("0")


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


# ---------------------------------------------------------------------------
# Operating Deficit Reserve (ODR) — Slice 4
# ---------------------------------------------------------------------------


def _odr_inputs(initial_occupancy_pct: float = 0.0) -> OperationalInputs:
    return OperationalInputs(
        initial_occupancy_pct=Decimal(str(initial_occupancy_pct)),
    )


def _odr_stream(rent_per_unit: float, unit_count: int, stab_occ: float = 95.0) -> IncomeStream:
    return IncomeStream(
        stream_type="residential_rent",
        label="Rent",
        amount_per_unit_monthly=Decimal(str(rent_per_unit)),
        unit_count=unit_count,
        stabilized_occupancy_pct=Decimal(str(stab_occ)),
        active_in_phases=["lease_up", "stabilized"],
    )


def _odr_opex(annual_amount: float, scale_with_lease_up: bool = False) -> OperatingExpenseLine:
    return OperatingExpenseLine(
        label="Operating Expenses",
        annual_amount=Decimal(str(annual_amount)),
        active_in_phases=["lease_up", "stabilized"],
        scale_with_lease_up=scale_with_lease_up,
    )


@pytest.mark.unit
def test_odr_zero_lease_up_months_returns_zero():
    """Spec §3.2 gating — ODR is not auto-created without a lease-up phase."""
    assert _odr_pool(
        streams=[_odr_stream(2000, 10)],
        expense_lines=[_odr_opex(120000)],
        inputs=_odr_inputs(),
        lease_up_months=0,
    ) == ZERO


@pytest.mark.unit
def test_odr_flat_opex_no_income_equals_total_opex():
    """With zero rent the deficit each month is the full OpEx."""
    pool = _odr_pool(
        streams=[],
        expense_lines=[_odr_opex(120000)],         # $10k / mo
        inputs=_odr_inputs(initial_occupancy_pct=0.0),
        lease_up_months=12,
    )
    # 12 × $10k = $120k
    assert pool == Decimal("120000.000000")


@pytest.mark.unit
def test_odr_income_at_or_above_opex_returns_zero():
    """Spec §3.2 — `max(OpEx − LUR, 0)` so over-coverage cannot reduce ODR below 0.

    Starting at stabilized occupancy from month 0 means LUR ≥ OpEx every
    month, even though the helper does still iterate. The clamp must hold.
    """
    pool = _odr_pool(
        streams=[_odr_stream(2000, 10)],           # 10 × $2000 × 0.95 = $19k / mo cap
        expense_lines=[_odr_opex(120000)],         # $10k / mo
        inputs=_odr_inputs(initial_occupancy_pct=95.0),
        lease_up_months=12,
    )
    assert pool == ZERO


@pytest.mark.unit
def test_odr_slower_absorption_produces_larger_pool():
    """Spec §3.2 endogenous window — slower ramp = bigger ODR.

    Same opex, same stabilized rent, but a 24-month ramp starting from 0%
    occupancy spends more months under-water than a 12-month ramp.
    """
    streams = [_odr_stream(1500, 10)]               # 10 × $1500 × 0.95 = $14,250 / mo cap
    expenses = [_odr_opex(120000)]                  # $10k / mo
    fast = _odr_pool(streams, expenses, _odr_inputs(0.0), lease_up_months=12)
    slow = _odr_pool(streams, expenses, _odr_inputs(0.0), lease_up_months=24)
    assert slow > fast
    assert fast > ZERO


@pytest.mark.unit
def test_odr_scale_with_lease_up_reduces_pool():
    """Expense lines flagged ``scale_with_lease_up`` ramp with occupancy
    too, so the early-month deficit is smaller than a flat-opex baseline."""
    streams = [_odr_stream(1500, 10)]
    flat = _odr_pool(
        streams=streams,
        expense_lines=[_odr_opex(120000, scale_with_lease_up=False)],
        inputs=_odr_inputs(0.0),
        lease_up_months=12,
    )
    ramped = _odr_pool(
        streams=streams,
        expense_lines=[_odr_opex(120000, scale_with_lease_up=True)],
        inputs=_odr_inputs(0.0),
        lease_up_months=12,
    )
    assert ramped < flat


@pytest.mark.unit
def test_odr_inactive_lines_ignored():
    """OpEx lines not active in the lease-up phase are excluded entirely."""
    inactive = OperatingExpenseLine(
        label="Stabilized-Only Reserve",
        annual_amount=Decimal("60000"),
        active_in_phases=["stabilized"],       # NOT in lease_up
    )
    pool = _odr_pool(
        streams=[],
        expense_lines=[_odr_opex(120000), inactive],
        inputs=_odr_inputs(),
        lease_up_months=6,
    )
    # Inactive line skipped → 6 × $10k from the active line only.
    assert pool == Decimal("60000.000000")


# ---------------------------------------------------------------------------
# Dev Fee basis bucket integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_odr_basis_bucket_registered():
    """``operating_deficit_reserve`` must be a recognized BASIS_BUCKETS key
    so the multi-source Dev Fee binding pipeline can include / exclude ODR
    via the standard ``basis_exclusions`` mechanism."""
    assert "operating_deficit_reserve" in BASIS_BUCKET_KEYS


@pytest.mark.unit
def test_odr_label_classifies_to_correct_bucket():
    """Unstamped legacy rows labeled "Operating Deficit Reserve" must
    classify to the new bucket via the label fallback path."""
    ul = UseLine(
        label="Operating Deficit Reserve",
        cost_category="soft",
    )
    assert classify_basis_bucket(ul) == "operating_deficit_reserve"


@pytest.mark.unit
def test_stamped_bucket_wins_over_label():
    """The stamped column is authoritative — preserves classification when
    the user renames the row."""
    ul = UseLine(
        label="Renamed By User",
        cost_category="soft",
        dev_fee_basis_bucket="operating_deficit_reserve",
    )
    assert classify_basis_bucket(ul) == "operating_deficit_reserve"
