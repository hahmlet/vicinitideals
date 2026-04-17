"""Unit tests for cashflow engine features added in April 2026.

Covers: balloon balance, LTL catchup, S-curve lease-up, bad debt/concessions,
dual-constraint sizing, debt yield, renovation absorption (continuous + discrete),
prepay penalty.

All tests are pure-function unit tests (no DB required).
"""
from __future__ import annotations

import math
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.cashflow import (
    LTL_CATCHUP_CAP_PCT,
    PhaseSpec,
    _balloon_balance,
    _compute_period,
    _growth_factor,
    _monthly_pmt,
    _stream_occupancy_pct,
)
from app.models.cashflow import PeriodType
from app.models.deal import IncomeStream, IncomeStreamType, OperationalInputs

ZERO = Decimal("0")
ONE = Decimal("1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inputs(**overrides) -> OperationalInputs:
    """Minimal OperationalInputs for unit testing."""
    defaults = {
        "project_id": uuid4(),
        "unit_count_new": 100,
        "hold_period_years": Decimal("5"),
        "exit_cap_rate_pct": Decimal("5.5"),
        "selling_costs_pct": Decimal("2.5"),
        "opex_per_unit_annual": Decimal("0"),
        "expense_growth_rate_pct_annual": Decimal("3"),
        "mgmt_fee_pct": Decimal("0"),
        "property_tax_annual": Decimal("0"),
        "insurance_annual": Decimal("0"),
        "capex_reserve_per_unit_annual": Decimal("0"),
        "initial_occupancy_pct": Decimal("50"),
        "lease_up_months": 9,
    }
    defaults.update(overrides)
    return OperationalInputs(**defaults)


def _make_stream(**overrides) -> IncomeStream:
    """Minimal IncomeStream for unit testing."""
    defaults = {
        "id": uuid4(),
        "project_id": uuid4(),
        "stream_type": IncomeStreamType.residential_rent,
        "label": "Test Rent",
        "unit_count": 100,
        "amount_per_unit_monthly": Decimal("1500"),
        "stabilized_occupancy_pct": Decimal("95"),
        "escalation_rate_pct_annual": Decimal("3"),
        "active_in_phases": ["lease_up", "stabilized"],
    }
    defaults.update(overrides)
    return IncomeStream(**defaults)


def _make_phase(period_type: PeriodType, months: int = 12) -> PhaseSpec:
    return PhaseSpec(period_type=period_type, months=months)


# ===========================================================================
# 1. Balloon Balance
# ===========================================================================

class TestBalloonBalance:
    """Test _balloon_balance for IO, amortizing, and IO-then-amort transitions."""

    @pytest.mark.unit
    def test_zero_principal_returns_zero(self):
        assert _balloon_balance(Decimal("0"), 6.0, 30, 60) == ZERO

    @pytest.mark.unit
    def test_no_rate_returns_full_principal(self):
        principal = Decimal("1000000")
        assert _balloon_balance(principal, None, 30, 60) == principal

    @pytest.mark.unit
    def test_io_period_returns_full_principal(self):
        """During IO period, balance should equal original principal."""
        principal = Decimal("1000000")
        balance = _balloon_balance(principal, 6.0, 30, months_elapsed=12, io_months=24)
        assert balance == principal

    @pytest.mark.unit
    def test_amortizing_reduces_balance(self):
        """After IO period, balance should decrease."""
        principal = Decimal("1000000")
        balance = _balloon_balance(principal, 6.0, 30, months_elapsed=60, io_months=0)
        assert balance < principal
        assert balance > ZERO

    @pytest.mark.unit
    def test_io_then_amort_transition(self):
        """Balance stays flat during IO, then decreases during amort."""
        principal = Decimal("1000000")
        # At month 12 (still IO)
        bal_io = _balloon_balance(principal, 6.0, 30, months_elapsed=12, io_months=24)
        # At month 36 (12 months into amort)
        bal_amort = _balloon_balance(principal, 6.0, 30, months_elapsed=36, io_months=24)
        assert bal_io == principal
        assert bal_amort < principal

    @pytest.mark.unit
    def test_long_amort_nearly_pays_off(self):
        """After 29 years of a 30yr loan, very little remains."""
        principal = Decimal("1000000")
        balance = _balloon_balance(principal, 5.0, 30, months_elapsed=348, io_months=0)
        # After 29 years, should have paid off most of the loan
        assert balance < principal * Decimal("0.10")

    @pytest.mark.unit
    def test_zero_rate_returns_full_principal(self):
        """Zero rate (0.0) is treated as no-interest — full balance outstanding.

        _balloon_balance treats rate_pct=0.0 as falsy (no amortization),
        consistent with _monthly_pmt which returns ZERO for rate=0.0.
        """
        principal = Decimal("120000")
        balance = _balloon_balance(principal, 0.0, 10, months_elapsed=60, io_months=0)
        assert balance == principal


# ===========================================================================
# 2. LTL Catchup Escalation
# ===========================================================================

class TestLTLCatchup:
    """Test the LTL catchup escalation logic in _compute_period."""

    @pytest.mark.unit
    def test_catchup_cap_constant_is_ten_percent(self):
        assert LTL_CATCHUP_CAP_PCT == Decimal("10")

    @pytest.mark.unit
    def test_catchup_escalation_year_one(self):
        """Year 1: $1200 in-place, $1500 target, 10% cap → increase $120."""
        stream = _make_stream(
            amount_per_unit_monthly=Decimal("1200"),
            catchup_target_rent=Decimal("1500"),
            unit_count=1,
            escalation_rate_pct_annual=Decimal("3"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized, months=60)

        # Period 12 = start of year 2 (year 1 complete)
        result = _compute_period(
            deal_model_id=uuid4(),
            period=12,
            phase=phase,
            month_index=0,
            inputs=inputs,
            streams=[stream],
            expense_lines=[],
            stabilized_noi_monthly=None,
            income_mode="revenue_opex",
        )
        # After 1 year: $1200 + min($300, $120) = $1320
        # The gross_revenue should reflect the catchup amount (1 unit)
        gross = result["gross_revenue"]
        assert Decimal("1310") < gross < Decimal("1330"), f"Expected ~$1320, got {gross}"

    @pytest.mark.unit
    def test_catchup_reaches_target_then_normal(self):
        """After gap is closed, should revert to normal escalation."""
        stream = _make_stream(
            amount_per_unit_monthly=Decimal("1200"),
            catchup_target_rent=Decimal("1260"),  # Small gap — closes in year 1
            unit_count=1,
            escalation_rate_pct_annual=Decimal("3"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized, months=60)

        # Period 24 = year 2 start. Gap was $60, cap is $120, so gap closed in year 1.
        # Year 2 should use normal 3% on $1260.
        result = _compute_period(
            deal_model_id=uuid4(),
            period=24,
            phase=phase,
            month_index=0,
            inputs=inputs,
            streams=[stream],
            expense_lines=[],
            stabilized_noi_monthly=None,
            income_mode="revenue_opex",
        )
        gross = result["gross_revenue"]
        # Year 1: $1200 → $1260 (gap closed). Year 2: $1260 × 1.03 = $1297.80
        assert Decimal("1290") < gross < Decimal("1305"), f"Expected ~$1298, got {gross}"

    @pytest.mark.unit
    def test_no_catchup_when_target_not_set(self):
        """Without catchup_target_rent, normal escalation applies."""
        stream = _make_stream(
            amount_per_unit_monthly=Decimal("1200"),
            unit_count=1,
            escalation_rate_pct_annual=Decimal("3"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized, months=60)

        result = _compute_period(
            deal_model_id=uuid4(),
            period=12,
            phase=phase,
            month_index=0,
            inputs=inputs,
            streams=[stream],
            expense_lines=[],
            stabilized_noi_monthly=None,
            income_mode="revenue_opex",
        )
        gross = result["gross_revenue"]
        # Normal: $1200 × 1.03 = $1236
        assert Decimal("1230") < gross < Decimal("1242"), f"Expected ~$1236, got {gross}"


# ===========================================================================
# 3. S-Curve Lease-Up
# ===========================================================================

class TestSCurveLeaseUp:
    """Test S-curve occupancy ramp vs linear."""

    @pytest.mark.unit
    def test_linear_ramp_midpoint(self):
        """Linear ramp: midpoint should be halfway between initial and stabilized."""
        stream = _make_stream(stabilized_occupancy_pct=Decimal("95"))
        inputs = _make_inputs(initial_occupancy_pct=Decimal("50"), lease_up_months=9)
        phase = _make_phase(PeriodType.lease_up, months=9)

        mid_occ = _stream_occupancy_pct(stream, phase, month_index=4, inputs=inputs)
        # Linear midpoint: 50 + (95-50) × 4/8 = 72.5%
        assert Decimal("0.72") < mid_occ < Decimal("0.73")

    @pytest.mark.unit
    def test_scurve_midpoint_near_linear_midpoint(self):
        """S-curve midpoint should be close to linear midpoint (sigmoid crosses ~0.5 at midpoint)."""
        stream = _make_stream(stabilized_occupancy_pct=Decimal("95"))
        inputs = _make_inputs(
            initial_occupancy_pct=Decimal("50"),
            lease_up_months=9,
            lease_up_curve="s_curve",
            lease_up_curve_steepness=Decimal("5"),
        )
        phase = _make_phase(PeriodType.lease_up, months=9)

        mid_occ = _stream_occupancy_pct(stream, phase, month_index=4, inputs=inputs)
        # S-curve midpoint should be ~72.5% (same as linear at midpoint)
        assert Decimal("0.70") < mid_occ < Decimal("0.75")

    @pytest.mark.unit
    def test_scurve_starts_slower_than_linear(self):
        """S-curve should have lower occupancy than linear at early months."""
        stream = _make_stream(stabilized_occupancy_pct=Decimal("95"))
        phase = _make_phase(PeriodType.lease_up, months=9)

        inputs_linear = _make_inputs(initial_occupancy_pct=Decimal("50"), lease_up_months=9)
        inputs_scurve = _make_inputs(
            initial_occupancy_pct=Decimal("50"),
            lease_up_months=9,
            lease_up_curve="s_curve",
            lease_up_curve_steepness=Decimal("8"),
        )

        linear_m1 = _stream_occupancy_pct(stream, phase, month_index=1, inputs=inputs_linear)
        scurve_m1 = _stream_occupancy_pct(stream, phase, month_index=1, inputs=inputs_scurve)

        assert scurve_m1 < linear_m1, f"S-curve ({scurve_m1}) should be slower than linear ({linear_m1}) early on"

    @pytest.mark.unit
    def test_scurve_endpoints_match(self):
        """S-curve must start at initial and end at stabilized."""
        stream = _make_stream(stabilized_occupancy_pct=Decimal("95"))
        inputs = _make_inputs(
            initial_occupancy_pct=Decimal("50"),
            lease_up_months=9,
            lease_up_curve="s_curve",
            lease_up_curve_steepness=Decimal("5"),
        )
        phase = _make_phase(PeriodType.lease_up, months=9)

        occ_start = _stream_occupancy_pct(stream, phase, month_index=0, inputs=inputs)
        occ_end = _stream_occupancy_pct(stream, phase, month_index=8, inputs=inputs)

        assert abs(occ_start - Decimal("0.50")) < Decimal("0.01"), f"Start should be ~50%, got {occ_start}"
        assert abs(occ_end - Decimal("0.95")) < Decimal("0.01"), f"End should be ~95%, got {occ_end}"


# ===========================================================================
# 4. Bad Debt & Concessions
# ===========================================================================

class TestBadDebtConcessions:
    """Test that bad_debt_pct and concessions_pct reduce income correctly."""

    @pytest.mark.unit
    def test_zero_defaults_no_impact(self):
        """With bad_debt=0 and concessions=0, income matches pre-feature behavior."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        assert result["gross_revenue"] == Decimal("1000.000000")
        assert result["effective_gross_income"] == Decimal("1000.000000")

    @pytest.mark.unit
    def test_bad_debt_reduces_egi(self):
        """Bad debt should reduce EGI below GPR × occupancy."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("5"),    # 5% of GPR
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        # GPR = $1000, occupancy 100%, bad debt 5% of GPR = $50
        # EGI = $1000 - $50 = $950
        assert result["gross_revenue"] == Decimal("1000.000000")
        egi = result["effective_gross_income"]
        assert Decimal("949") < egi < Decimal("951"), f"Expected ~$950, got {egi}"

    @pytest.mark.unit
    def test_concessions_reduce_egi(self):
        """Concessions should reduce EGI similarly to bad debt."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("3"),  # 3% of GPR
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        egi = result["effective_gross_income"]
        assert Decimal("969") < egi < Decimal("971"), f"Expected ~$970, got {egi}"

    @pytest.mark.unit
    def test_combined_bad_debt_and_concessions(self):
        """Bad debt + concessions should stack additively."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("90"),   # 10% vacancy
            bad_debt_pct=Decimal("2"),
            concessions_pct=Decimal("3"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        # GPR = $1000, after vacancy (90%) = $900, bad debt 2% of $1000 = $20, concessions 3% = $30
        # EGI = $900 - $20 - $30 = $850
        egi = result["effective_gross_income"]
        assert Decimal("849") < egi < Decimal("851"), f"Expected ~$850, got {egi}"

    @pytest.mark.unit
    def test_bad_debt_in_line_item_adjustments(self):
        """Bad debt and concessions should appear in line item adjustments."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("5"),
            concessions_pct=Decimal("3"),
        )
        inputs = _make_inputs()
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        income_items = [li for li in result["line_items"] if li.category == "income"]
        assert len(income_items) == 1
        adj = income_items[0].adjustments
        assert "bad_debt" in adj
        assert "concessions" in adj
        assert float(adj["bad_debt_pct"]) == pytest.approx(5.0, abs=0.1)
        assert float(adj["concessions_pct"]) == pytest.approx(3.0, abs=0.1)


# ===========================================================================
# 5. Renovation Absorption (Continuous)
# ===========================================================================

class TestRenovationAbsorption:
    """Test continuous renovation absorption rate."""

    @pytest.mark.unit
    def test_no_absorption_full_income(self):
        """Without absorption rate, full income from period 0."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs(renovation_months=6, lease_up_months=3)
        phase = _make_phase(PeriodType.stabilized)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        assert result["gross_revenue"] == Decimal("1000.000000")

    @pytest.mark.unit
    def test_absorption_reduces_early_income(self):
        """With absorption=1.0 in reno phase, early months should have reduced income."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            renovation_absorption_rate=Decimal("1"),
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs(renovation_months=6, lease_up_months=3)
        phase = _make_phase(PeriodType.minor_renovation, months=6)
        result = _compute_period(
            deal_model_id=uuid4(), period=0, phase=phase, month_index=0,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        # Period 0 of 9 total reno+leaseup months: absorption = 1/9 ≈ 11%
        gross = result["gross_revenue"]
        assert gross < Decimal("200"), f"Expected reduced income at period 0, got {gross}"

    @pytest.mark.unit
    def test_discrete_capture_schedule(self):
        """Capture schedule overrides continuous ramp with year-by-year steps."""
        stream = _make_stream(
            unit_count=1,
            amount_per_unit_monthly=Decimal("1000"),
            stabilized_occupancy_pct=Decimal("100"),
            renovation_absorption_rate=Decimal("1"),
            renovation_capture_schedule=[
                {"year": 1, "capture_pct": 0},
                {"year": 2, "capture_pct": 50},
                {"year": 3, "capture_pct": 100},
            ],
            bad_debt_pct=Decimal("0"),
            concessions_pct=Decimal("0"),
        )
        inputs = _make_inputs()

        # Year 1 (period 6): capture = 0%
        phase = _make_phase(PeriodType.lease_up, months=12)
        result_y1 = _compute_period(
            deal_model_id=uuid4(), period=6, phase=phase, month_index=6,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        assert result_y1["gross_revenue"] == ZERO

        # Year 2 (period 18): capture = 50%
        phase_stab = _make_phase(PeriodType.stabilized, months=60)
        result_y2 = _compute_period(
            deal_model_id=uuid4(), period=18, phase=phase_stab, month_index=6,
            inputs=inputs, streams=[stream], expense_lines=[],
            stabilized_noi_monthly=None, income_mode="revenue_opex",
        )
        gross_y2 = result_y2["gross_revenue"]
        # 50% of $1000 × escalation at month 18 (~1.03^1.5 ≈ 1.045) ≈ $522
        assert Decimal("480") < gross_y2 < Decimal("540"), f"Expected ~$500-525 at 50% capture + escalation, got {gross_y2}"


# ===========================================================================
# 6. Growth Factor (existing, verify no regression)
# ===========================================================================

class TestGrowthFactor:
    """Verify _growth_factor behavior."""

    @pytest.mark.unit
    def test_zero_rate_returns_one(self):
        assert _growth_factor(Decimal("0"), 12) == ONE

    @pytest.mark.unit
    def test_zero_period_returns_one(self):
        assert _growth_factor(Decimal("3"), 0) == ONE

    @pytest.mark.unit
    def test_three_pct_at_twelve_months(self):
        """3% annual rate at month 12 = 1.03 exactly."""
        factor = _growth_factor(Decimal("3"), 12)
        assert abs(factor - Decimal("1.03")) < Decimal("0.0001")

    @pytest.mark.unit
    def test_three_pct_at_24_months(self):
        """3% annual at month 24 = 1.03^2 = 1.0609."""
        factor = _growth_factor(Decimal("3"), 24)
        assert abs(factor - Decimal("1.0609")) < Decimal("0.001")


# ===========================================================================
# 7. Monthly Payment (verify for balloon calc)
# ===========================================================================

class TestMonthlyPmt:
    """Verify _monthly_pmt produces correct amortization payments."""

    @pytest.mark.unit
    def test_standard_30yr_6pct(self):
        """$1M at 6% over 30yr should be ~$5,996/mo."""
        pmt = _monthly_pmt(Decimal("1000000"), 6.0, 30)
        assert Decimal("5990") < pmt < Decimal("6002")

    @pytest.mark.unit
    def test_no_rate_returns_zero(self):
        assert _monthly_pmt(Decimal("1000000"), None, 30) == ZERO

    @pytest.mark.unit
    def test_zero_rate_returns_zero(self):
        """0% rate is falsy in _monthly_pmt — returns ZERO (no payments on zero-rate debt)."""
        pmt = _monthly_pmt(Decimal("120000"), 0.0, 10)
        assert pmt == ZERO


# ===========================================================================
# 8. Schema Round-Trip Tests
# ===========================================================================

class TestSchemaRoundTrip:
    """Test that new Pydantic schema fields serialize and deserialize."""

    @pytest.mark.unit
    def test_income_stream_new_fields(self):
        from app.schemas.deal import IncomeStreamBase
        data = {
            "stream_type": "residential_rent",
            "label": "1BR Rent",
            "bad_debt_pct": "2.5",
            "concessions_pct": "3.0",
            "renovation_absorption_rate": "1.0",
            "renovation_capture_schedule": [{"year": 1, "capture_pct": 0}],
            "catchup_target_rent": "1500.00",
            "escalation_rate_pct_annual": "3.0",
        }
        obj = IncomeStreamBase.model_validate(data)
        assert obj.bad_debt_pct == Decimal("2.5")
        assert obj.concessions_pct == Decimal("3.0")
        assert obj.renovation_absorption_rate == Decimal("1.0")
        assert obj.catchup_target_rent == Decimal("1500.00")
        assert len(obj.renovation_capture_schedule) == 1
        dumped = obj.model_dump(mode="json")
        assert "bad_debt_pct" in dumped
        assert "catchup_target_rent" in dumped
        assert "renovation_capture_schedule" in dumped

    @pytest.mark.unit
    def test_unit_mix_new_fields(self):
        from app.schemas.deal import UnitMixBase
        data = {
            "label": "1BR/1BA",
            "unit_count": 80,
            "market_rent_per_unit": "1500.00",
            "in_place_rent_per_unit": "1200.00",
            "unit_strategy": "ltl_catchup",
            "post_reno_rent_per_unit": None,
        }
        obj = UnitMixBase.model_validate(data)
        assert obj.market_rent_per_unit == Decimal("1500.00")
        assert obj.in_place_rent_per_unit == Decimal("1200.00")
        assert obj.unit_strategy == "ltl_catchup"
        dumped = obj.model_dump(mode="json")
        assert "market_rent_per_unit" in dumped
        assert "unit_strategy" in dumped

    @pytest.mark.unit
    def test_operational_inputs_new_fields(self):
        from app.schemas.deal import OperationalInputsBase
        data = {
            "lease_up_curve": "s_curve",
            "lease_up_curve_steepness": "7.5",
            "asset_mgmt_fee_pct": "1.5",
        }
        obj = OperationalInputsBase.model_validate(data)
        assert obj.lease_up_curve == "s_curve"
        assert obj.lease_up_curve_steepness == Decimal("7.5")
        assert obj.asset_mgmt_fee_pct == Decimal("1.5")

    @pytest.mark.unit
    def test_operational_outputs_new_fields(self):
        from app.schemas.deal import OperationalOutputsBase
        data = {
            "debt_yield_pct": "9.5",
            "sensitivity_matrix": {"param_x": "exit_cap", "values": [[1, 2], [3, 4]]},
        }
        obj = OperationalOutputsBase.model_validate(data)
        assert obj.debt_yield_pct == Decimal("9.5")
        assert obj.sensitivity_matrix["param_x"] == "exit_cap"

    @pytest.mark.unit
    def test_capital_source_schema_new_fields(self):
        from app.schemas.capital import CapitalSourceSchema
        data = {
            "amount": "1000000",
            "interest_rate_pct": 6.5,
            "refi_cap_rate_pct": 5.5,
            "prepay_penalty_pct": 1.0,
        }
        obj = CapitalSourceSchema.model_validate(data)
        assert obj.refi_cap_rate_pct == 5.5
        assert obj.prepay_penalty_pct == 1.0
        dumped = obj.model_dump(mode="json")
        assert "refi_cap_rate_pct" in dumped
        assert "prepay_penalty_pct" in dumped
