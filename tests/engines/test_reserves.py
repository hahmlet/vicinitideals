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

from app.engines.cashflow import (
    _draw_schedule_for,
    _ir_lease_up_pool,
    _odr_pool,
    _validate_stabilization_anchor,
)
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


# ---------------------------------------------------------------------------
# LUR sweep in _compute_period — Slice 5a
# ---------------------------------------------------------------------------


from uuid import uuid4                                       # noqa: E402
from app.engines.cashflow import _compute_period             # noqa: E402
from app.engines.phase_plan import PhaseSpec                 # noqa: E402
from app.models.cashflow import PeriodType                   # noqa: E402


def _stab_inputs(initial_occupancy_pct: float = 95.0) -> OperationalInputs:
    """Inputs that produce non-zero NOI during the lease-up phase used in
    the sweep tests. Stab cap rate / mgmt fee zeroed so the math is
    transparent."""
    return OperationalInputs(
        project_id=uuid4(),
        unit_count_new=10,
        initial_occupancy_pct=Decimal(str(initial_occupancy_pct)),
        opex_per_unit_annual=Decimal("0"),
        expense_growth_rate_pct_annual=Decimal("0"),
        mgmt_fee_pct=Decimal("0"),
        property_tax_annual=Decimal("0"),
        insurance_annual=Decimal("0"),
        capex_reserve_per_unit_annual=Decimal("0"),
        exit_cap_rate_pct=Decimal("5"),
        selling_costs_pct=Decimal("2"),
    )


def _lease_up_stream(rent: float, units: int, stab_occ: float = 95.0) -> IncomeStream:
    pid = uuid4()
    return IncomeStream(
        project_id=pid,
        stream_type="residential_rent",
        label="Rent",
        amount_per_unit_monthly=Decimal(str(rent)),
        unit_count=units,
        stabilized_occupancy_pct=Decimal(str(stab_occ)),
        active_in_phases=["lease_up", "stabilized"],
    )


@pytest.mark.unit
def test_lur_sweep_replaces_ir_income_coverage_during_lease_up():
    """Spec §3 — IR pays 100% of interest during lease-up; excess NOI
    sweeps to principal. The pre-spec ``debt_service`` inflation by
    ``min(ir_lease_up_interest, max(0, noi))`` must be gone, replaced by
    a real cash outflow that reduces ``net_cash_flow``.
    """
    result = _compute_period(
        deal_model_id=uuid4(),
        period=0,
        phase=PhaseSpec(PeriodType.lease_up, 12),
        month_index=11,                                  # late lease-up: occupancy ramped up
        inputs=_stab_inputs(initial_occupancy_pct=95.0),
        streams=[_lease_up_stream(2000, 10)],            # 10 × $2000 × 0.95 = $19k / mo
        expense_lines=[],
        stabilized_noi_monthly=None,
        construction_debt_monthly=ZERO,
        operation_debt_monthly=ZERO,
        ir_lease_up_interest=Decimal("5000"),
    )

    # DS unchanged from the input — IR pays the sized interest from its own
    # pool, not by routing NOI through `debt_service`.
    assert result["debt_service"] == ZERO
    # Excess NOI sweeps; sweep amount equals NOI (post-OpEx, post-capex).
    assert result["lur_sweep"] > ZERO
    assert result["lur_sweep"] == result["noi"]
    # Distributable cash = NOI − DS − sweep = 0 during lease-up under spec.
    assert result["net_cash_flow"] == ZERO

    sweep_rows = [
        li for li in result["line_items"]
        if getattr(li, "label", "") == "LUR Sweep to Principal"
    ]
    assert len(sweep_rows) == 1
    meta = sweep_rows[0].adjustments or {}
    assert meta.get("applies_to") == "payoff_balance_only"


@pytest.mark.unit
def test_lur_sweep_zero_when_noi_zero():
    """No NOI → no sweep. DS still zero (IR pays it)."""
    result = _compute_period(
        deal_model_id=uuid4(),
        period=0,
        phase=PhaseSpec(PeriodType.lease_up, 12),
        month_index=0,
        inputs=_stab_inputs(initial_occupancy_pct=0.0),
        streams=[],                                       # no revenue
        expense_lines=[],
        stabilized_noi_monthly=None,
        ir_lease_up_interest=Decimal("5000"),
    )
    assert result["debt_service"] == ZERO
    assert result["lur_sweep"] == ZERO
    sweep_rows = [
        li for li in result["line_items"]
        if getattr(li, "label", "") == "LUR Sweep to Principal"
    ]
    assert sweep_rows == []


@pytest.mark.unit
def test_lur_sweep_absent_outside_ir_window():
    """Stabilized periods don't sweep — sized DS comes from operations now."""
    result = _compute_period(
        deal_model_id=uuid4(),
        period=12,
        phase=PhaseSpec(PeriodType.stabilized, 12),
        month_index=0,
        inputs=_stab_inputs(initial_occupancy_pct=95.0),
        streams=[_lease_up_stream(2000, 10)],
        expense_lines=[],
        stabilized_noi_monthly=None,
        operation_debt_monthly=Decimal("3000"),
        ir_lease_up_interest=Decimal("5000"),             # passed but inert in stab
    )
    # Sized DS flows through; no sweep.
    assert result["debt_service"] == Decimal("3000")
    assert result["lur_sweep"] == ZERO


@pytest.mark.unit
def test_interest_invariance_to_lur_sweep():
    """Spec §7 / critique #2 — total interest the lender accrues over the
    lease-up window must be independent of how much LUR shows up. The
    period helper does not recompute interest; it accepts the sized
    monthly amount as a parameter. So whether the period has heavy or
    zero revenue, the IR-funded interest the helper sees is constant.
    This locks the contract that the period helper never touches
    ``ir_lease_up_interest`` when handling the sweep.
    """
    sized_interest = Decimal("5000")
    zero_rev = _compute_period(
        deal_model_id=uuid4(),
        period=0,
        phase=PhaseSpec(PeriodType.lease_up, 12),
        month_index=0,
        inputs=_stab_inputs(initial_occupancy_pct=0.0),
        streams=[],
        expense_lines=[],
        stabilized_noi_monthly=None,
        ir_lease_up_interest=sized_interest,
    )
    full_rev = _compute_period(
        deal_model_id=uuid4(),
        period=0,
        phase=PhaseSpec(PeriodType.lease_up, 12),
        month_index=11,
        inputs=_stab_inputs(initial_occupancy_pct=95.0),
        streams=[_lease_up_stream(2000, 10)],
        expense_lines=[],
        stabilized_noi_monthly=None,
        ir_lease_up_interest=sized_interest,
    )
    # Sized interest is not echoed into `debt_service` in either case;
    # the IR pool funds it externally to the period loop. The lender's
    # accrual is therefore invariant to NOI — the LUR sweep doesn't
    # shrink it.
    assert zero_rev["debt_service"] == ZERO
    assert full_rev["debt_service"] == ZERO


# ──────────────────────────────────────────────────────────────────────────
# Stabilization-anchor validator (Slice 5d, critique #4)
# ──────────────────────────────────────────────────────────────────────────


def _cf_row(period: int, noi: float, ds: float) -> SimpleNamespace:
    """Minimal cash-flow row stand-in. _validate_stabilization_anchor only
    reads .period / .noi / .debt_service.
    """
    return SimpleNamespace(
        period=period,
        noi=Decimal(str(noi)),
        debt_service=Decimal(str(ds)),
    )


@pytest.mark.unit
def test_stabilization_anchor_matches_curve_returns_none():
    """User anchor lines up with the curve-derived NOI≥DS month — no
    warning, no error, validator returns None.
    """
    rows = [
        _cf_row(0, 0, 3000),     # lease-up month 0: NOI = 0
        _cf_row(1, 1000, 3000),  # ramp
        _cf_row(2, 2500, 3000),  # still short
        _cf_row(3, 3500, 3000),  # NOI catches DS here
        _cf_row(4, 4000, 3000),  # stabilized
    ]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=3,
    )
    assert result is None


@pytest.mark.unit
def test_stabilization_anchor_earlier_than_curve_returns_error():
    """User anchors Stabilization BEFORE the curve catches DS — IR window
    ends prematurely and OR is being asked to absorb what should still be
    IR coverage. Validator must return ``status="error"``.
    """
    rows = [
        _cf_row(0, 0, 3000),
        _cf_row(1, 1000, 3000),
        _cf_row(2, 2500, 3000),
        _cf_row(3, 3500, 3000),  # curve catches DS
    ]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=1,  # anchored 2 months too early
    )
    assert result is not None
    assert result["status"] == "error"
    assert result["curve_derived_period"] == 3
    assert result["anchored_period"] == 1
    assert result["gap_months"] == -2
    assert "Operating Reserve" in result["message"]


@pytest.mark.unit
def test_stabilization_anchor_later_than_curve_returns_warning():
    """User anchors Stabilization AFTER the curve catches DS — deal still
    pencils but OR is sized for a longer runway than needed. Validator
    returns ``status="warning"``.
    """
    rows = [
        _cf_row(0, 0, 3000),
        _cf_row(1, 3500, 3000),  # curve catches DS very early
        _cf_row(2, 4000, 3000),
        _cf_row(3, 4500, 3000),
        _cf_row(4, 5000, 3000),
        _cf_row(5, 5000, 3000),
    ]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=5,  # anchored 4 months later than needed
    )
    assert result is not None
    assert result["status"] == "warning"
    assert result["curve_derived_period"] == 1
    assert result["anchored_period"] == 5
    assert result["gap_months"] == 4


@pytest.mark.unit
def test_stabilization_anchor_noi_never_catches_ds_returns_none():
    """Deal under-performs the debt — NOI < DS in every modeled month.
    There is no curve-derived Stabilization month; the validator returns
    None and lets the proof's ``is_solvent`` flag surface the real issue
    (the deal itself, not the anchor placement).
    """
    rows = [
        _cf_row(0, 0, 3000),
        _cf_row(1, 500, 3000),
        _cf_row(2, 1000, 3000),
        _cf_row(3, 1500, 3000),
        _cf_row(4, 2000, 3000),
    ]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=4,
    )
    assert result is None


@pytest.mark.unit
def test_stabilization_anchor_skips_months_with_zero_ds():
    """Months with DS == 0 (post-payoff, fully IR-funded with sweep, etc.)
    are not meaningful for the NOI≥DS comparison — they would trivially
    satisfy the inequality and skew the curve-derived month earlier than
    the real lender-coverage point. Validator must skip them.
    """
    rows = [
        _cf_row(0, 0, 0),        # IR window — DS funded by reserve; skip
        _cf_row(1, 100, 0),      # same; should not match curve here
        _cf_row(2, 2000, 3000),  # DS appears; NOI short
        _cf_row(3, 3500, 3000),  # NOI catches DS here
    ]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=3,
    )
    # Anchor matches the curve-derived period 3.
    assert result is None


@pytest.mark.unit
def test_stabilization_anchor_no_rows_returns_none():
    """No cash-flow rows means nothing to evaluate. Validator must not
    raise; it returns None and lets the proof short-circuit.
    """
    result = _validate_stabilization_anchor(
        cash_flow_rows=[],
        co_period=0,
        stabilized_period=12,
    )
    assert result is None


@pytest.mark.unit
def test_stabilization_anchor_missing_stab_period_returns_none():
    """The proof passes ``stab_period=None`` when no stabilized phase is
    present in the timeline (acquisition-only deals). Validator must
    short-circuit cleanly.
    """
    rows = [_cf_row(0, 0, 3000), _cf_row(1, 3500, 3000)]
    result = _validate_stabilization_anchor(
        cash_flow_rows=rows,
        co_period=0,
        stabilized_period=None,
    )
    assert result is None
