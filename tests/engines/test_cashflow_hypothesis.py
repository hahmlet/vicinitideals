from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.engines.cashflow import (
    PhaseSpec,
    _balloon_balance,
    _compute_period,
    _growth_factor,
    _stream_occupancy_pct,
)
from app.models.cashflow import PeriodType
from app.models.deal import IncomeStream, IncomeStreamType, OperationalInputs


# Keep runs deterministic enough for CI while still exploring broad input space.
settings.register_profile(
    "engine_props",
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("engine_props")


def _quant(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def _money_strategy(min_value: str, max_value: str) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def _period_case(draw) -> tuple[OperationalInputs, IncomeStream, PhaseSpec, int, int, Decimal, Decimal]:
    unit_count = draw(st.integers(min_value=1, max_value=400))
    phase_type = draw(st.sampled_from([PeriodType.lease_up, PeriodType.stabilized]))
    phase_months = draw(st.integers(min_value=2, max_value=36))
    month_index = draw(st.integers(min_value=0, max_value=phase_months - 1))
    period = draw(st.integers(min_value=0, max_value=360))

    stabilized_occ = draw(_money_strategy("60", "100"))
    initial_occ = draw(_money_strategy("0", str(stabilized_occ)))

    bad_debt_pct = draw(_money_strategy("0", "12"))
    concessions_pct = draw(_money_strategy("0", "12"))

    stream = IncomeStream(
        id=uuid4(),
        project_id=uuid4(),
        stream_type=IncomeStreamType.residential_rent,
        label="Generated Rent",
        unit_count=unit_count,
        amount_per_unit_monthly=draw(_money_strategy("400", "9000")),
        stabilized_occupancy_pct=stabilized_occ,
        bad_debt_pct=bad_debt_pct,
        concessions_pct=concessions_pct,
        escalation_rate_pct_annual=draw(_money_strategy("0", "9")),
        active_in_phases=["lease_up", "stabilized", "exit"],
    )

    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=unit_count,
        lease_up_months=phase_months,
        initial_occupancy_pct=initial_occ,
        opex_per_unit_annual=draw(_money_strategy("0", "12000")),
        expense_growth_rate_pct_annual=draw(_money_strategy("0", "8")),
        mgmt_fee_pct=draw(_money_strategy("0", "12")),
        property_tax_annual=draw(_money_strategy("0", "150000")),
        insurance_annual=draw(_money_strategy("0", "80000")),
        capex_reserve_per_unit_annual=draw(_money_strategy("0", "1600")),
        exit_cap_rate_pct=draw(_money_strategy("4", "12")),
        selling_costs_pct=draw(_money_strategy("0", "6")),
    )

    construction_debt_monthly = draw(_money_strategy("0", "40000"))
    operation_debt_monthly = draw(_money_strategy("0", "40000"))

    return (
        inputs,
        stream,
        PhaseSpec(phase_type, phase_months),
        month_index,
        period,
        construction_debt_monthly,
        operation_debt_monthly,
    )


@pytest.mark.unit
@given(case=_period_case())
def test_compute_period_accounting_identity(case) -> None:
    (
        inputs,
        stream,
        phase,
        month_index,
        period,
        construction_debt_monthly,
        operation_debt_monthly,
    ) = case

    result = _compute_period(
        deal_model_id=uuid4(),
        period=period,
        phase=phase,
        month_index=month_index,
        inputs=inputs,
        streams=[stream],
        expense_lines=[],
        stabilized_noi_monthly=None,
        construction_debt_monthly=construction_debt_monthly,
        operation_debt_monthly=operation_debt_monthly,
    )

    assert result["noi"] == _quant(
        result["effective_gross_income"] - result["operating_expenses"] - result["capex_reserve"]
    )
    assert result["net_cash_flow"] == _quant(result["noi"] - result["debt_service"])


@pytest.mark.unit
@given(case=_period_case())
def test_compute_period_income_bounds(case) -> None:
    inputs, stream, phase, month_index, period, _, _ = case

    result = _compute_period(
        deal_model_id=uuid4(),
        period=period,
        phase=phase,
        month_index=month_index,
        inputs=inputs,
        streams=[stream],
        expense_lines=[],
        stabilized_noi_monthly=None,
    )

    assert result["gross_revenue"] >= Decimal("0")
    assert result["vacancy_loss"] >= Decimal("0")
    assert result["effective_gross_income"] >= Decimal("0")
    assert result["effective_gross_income"] <= result["gross_revenue"]


@pytest.mark.unit
@given(
    stabilized_occ=_money_strategy("60", "100"),
    initial_occ=_money_strategy("0", "60"),
    months=st.integers(min_value=2, max_value=24),
    curve=st.sampled_from(["linear", "s_curve"]),
    steepness=_money_strategy("1", "12"),
)
def test_stream_occupancy_stays_within_expected_bounds(
    stabilized_occ: Decimal,
    initial_occ: Decimal,
    months: int,
    curve: str,
    steepness: Decimal,
) -> None:
    # Ensure initial occupancy does not exceed stabilized occupancy.
    if initial_occ > stabilized_occ:
        initial_occ = stabilized_occ

    stream = IncomeStream(
        id=uuid4(),
        project_id=uuid4(),
        stream_type=IncomeStreamType.residential_rent,
        label="Generated Stream",
        unit_count=50,
        amount_per_unit_monthly=Decimal("1500"),
        stabilized_occupancy_pct=stabilized_occ,
        escalation_rate_pct_annual=Decimal("3"),
        active_in_phases=["lease_up", "stabilized"],
    )
    inputs = OperationalInputs(
        project_id=uuid4(),
        unit_count_new=50,
        initial_occupancy_pct=initial_occ,
        lease_up_months=months,
        lease_up_curve=curve,
        lease_up_curve_steepness=steepness,
        opex_per_unit_annual=Decimal("0"),
        expense_growth_rate_pct_annual=Decimal("3"),
        mgmt_fee_pct=Decimal("0"),
        property_tax_annual=Decimal("0"),
        insurance_annual=Decimal("0"),
        capex_reserve_per_unit_annual=Decimal("0"),
        exit_cap_rate_pct=Decimal("5.5"),
        selling_costs_pct=Decimal("2.0"),
    )
    phase = PhaseSpec(PeriodType.lease_up, months)

    occupancies = [
        _stream_occupancy_pct(stream, phase, i, inputs)
        for i in range(months)
    ]

    lower = (initial_occ / Decimal("100")).quantize(Decimal("0.000001"))
    upper = (stabilized_occ / Decimal("100")).quantize(Decimal("0.000001"))

    assert all(lower <= occ <= upper for occ in occupancies)
    assert all(occupancies[i] <= occupancies[i + 1] for i in range(len(occupancies) - 1))


@pytest.mark.unit
@given(
    principal=_money_strategy("1000", "10000000"),
    rate_pct=_money_strategy("0", "15"),
    amort_years=st.integers(min_value=1, max_value=40),
    io_months=st.integers(min_value=0, max_value=120),
    m1=st.integers(min_value=0, max_value=360),
    m2=st.integers(min_value=0, max_value=360),
)
def test_balloon_balance_is_monotone_nonincreasing(
    principal: Decimal,
    rate_pct: Decimal,
    amort_years: int,
    io_months: int,
    m1: int,
    m2: int,
) -> None:
    start_month = min(m1, m2)
    end_month = max(m1, m2)

    bal_start = _balloon_balance(
        principal=principal,
        rate_pct=float(rate_pct),
        amort_years=amort_years,
        months_elapsed=start_month,
        io_months=io_months,
    )
    bal_end = _balloon_balance(
        principal=principal,
        rate_pct=float(rate_pct),
        amort_years=amort_years,
        months_elapsed=end_month,
        io_months=io_months,
    )

    assert Decimal("0") <= bal_end <= bal_start <= principal


@pytest.mark.unit
@given(
    rate_pct=_money_strategy("0", "15"),
    period=st.integers(min_value=0, max_value=360),
)
def test_growth_factor_nonnegative_rates_never_drop_below_one(
    rate_pct: Decimal,
    period: int,
) -> None:
    gf = _growth_factor(rate_pct, period)
    assert gf >= Decimal("1")

    if period == 0:
        assert gf == Decimal("1.000000")
