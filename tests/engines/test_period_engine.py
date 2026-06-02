"""
Unit tests for app/engines/period_engine.py

Phase A tests — pure period engine, no cashflow.py or draw_schedule.py integration.
Each test exercises one carry type or one invariant in isolation.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.engines.period_engine import (
    LoanSpec,
    PeriodEngineInputs,
    PhaseSpec,
    run_period_engine,
)

ZERO = Decimal("0")
ONE = Decimal("1")


def _phase(n: int, period_type: str = "construction") -> PhaseSpec:
    return PhaseSpec(period_type=period_type, n_months=n)


def _loan(
    module_id: str = "loan-1",
    carry_type: str = "io_only",
    principal: str = "1000000",
    rate_pct: str = "6.0",
    active_from: int = 0,
    active_to: int = 11,
    amort_years: int = 30,
) -> LoanSpec:
    return LoanSpec(
        module_id=module_id,
        carry_type=carry_type,
        principal=Decimal(principal),
        rate_pct=Decimal(rate_pct),
        active_from_period=active_from,
        active_to_period=active_to,
        amort_years=amort_years,
    )


# ---------------------------------------------------------------------------
# IO-Only carry
# ---------------------------------------------------------------------------

class TestIOOnlyCarry:
    def test_balance_stays_flat(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[_loan(carry_type="io_only", active_from=0, active_to=11)],
        ))
        principal = Decimal("1000000")
        for row in rows[1:]:  # skip period 0 (activation period)
            detail = row.loans[0]
            assert detail.balance_open == principal
            assert detail.balance_close == principal

    def test_monthly_payment_formula(self):
        # P × rate / 1200 = 1_000_000 × 6 / 1200 = 5_000
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="io_only", rate_pct="6.0", active_from=0, active_to=2)],
        ))
        expected = Decimal("1000000") * Decimal("6") / Decimal("1200")
        for row in rows:
            detail = row.loans[0]
            assert detail.interest_paid == expected.quantize(Decimal("0.000001"))

    def test_bank_balance_decreases_by_interest(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="io_only", rate_pct="6.0", active_from=0, active_to=2)],
            opening_cash_balance=Decimal("100000"),
        ))
        monthly_interest = Decimal("1000000") * Decimal("6") / Decimal("1200")
        # Period 0: draw 1_000_000 in, pay interest out
        assert rows[0].bank_balance_close == Decimal("100000") + Decimal("1000000") - monthly_interest
        # Period 1: only interest out
        assert rows[1].bank_balance_close == rows[0].bank_balance_close - monthly_interest

    def test_no_accrual_no_principal_paid(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="io_only", active_from=0, active_to=5)],
        ))
        for row in rows:
            assert row.loans[0].interest_accrued == ZERO
            assert row.loans[0].principal_paid == ZERO


# ---------------------------------------------------------------------------
# Interest Reserve carry
# ---------------------------------------------------------------------------

class TestInterestReserveCarry:
    def test_pool_drawn_monthly(self):
        # 12-month window; pool = P × r/1200 × (12+1)/2
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[_loan(carry_type="interest_reserve", rate_pct="6.0", active_from=0, active_to=11)],
        ))
        monthly_interest = Decimal("1000000") * Decimal("6") / Decimal("1200")
        expected_pool_initial = (monthly_interest * Decimal("13") / Decimal("2")).quantize(Decimal("0.000001"))

        # Period 0: pool funded at initial, then first month drawn
        row0 = rows[0]
        detail0 = row0.loans[0]
        assert detail0.ir_pool_open == ZERO   # before funding
        assert detail0.ir_pool_close == expected_pool_initial - monthly_interest

        # Each subsequent period pool decreases by monthly_interest
        for i in range(1, 12):
            expected_close = expected_pool_initial - monthly_interest * Decimal(i + 1)
            actual_close = rows[i].loans[0].ir_pool_close
            assert abs(actual_close - expected_close.quantize(Decimal("0.000001"))) < Decimal("0.01")

    def test_balance_stays_flat(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[_loan(carry_type="interest_reserve", active_from=0, active_to=11)],
        ))
        principal = Decimal("1000000")
        for row in rows[1:]:
            assert row.loans[0].balance_close == principal

    def test_ir_does_not_reduce_bank_balance(self):
        # IR interest comes from pre-funded pool, not operating account
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="interest_reserve", rate_pct="6.0", active_from=0, active_to=5)],
            opening_cash_balance=Decimal("500000"),
        ))
        # After activation: bank balance = opening + draw received (principal)
        # No interest leaves bank balance for IR carry
        assert rows[0].bank_balance_close == Decimal("500000") + Decimal("1000000")
        # Stays constant (no uses, no income, no IO/PI interest)
        for row in rows[1:]:
            assert row.bank_balance_close == rows[0].bank_balance_close

    def test_pool_exhaustion_does_not_floor_violation_alone(self):
        # Pool runs out in month 7 (13/2 months of interest ≈ 6.5 months)
        # Floor violation depends on bank_balance_close < reserve_floor, not pool itself
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[_loan(carry_type="interest_reserve", rate_pct="6.0", active_from=0, active_to=11)],
            reserve_floor_by_period={m: ZERO for m in range(12)},
        ))
        # Bank balance is unaffected by IR pool state — no violations at floor=0
        assert all(not row.floor_violation for row in rows)

    def test_ir_pool_override(self):
        override = Decimal("30000")
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[LoanSpec(
                module_id="loan-ir",
                carry_type="interest_reserve",
                principal=Decimal("1000000"),
                rate_pct=Decimal("6.0"),
                active_from_period=0,
                active_to_period=2,
                ir_pool_override=override,
            )],
        ))
        monthly = Decimal("1000000") * Decimal("6") / Decimal("1200")
        assert rows[0].loans[0].ir_pool_close == (override - monthly).quantize(Decimal("0.000001"))


# ---------------------------------------------------------------------------
# Capitalized Interest carry
# ---------------------------------------------------------------------------

class TestCapitalizedInterestCarry:
    def test_balance_compounds_monthly(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[_loan(carry_type="capitalized_interest", rate_pct="6.0", active_from=0, active_to=11)],
        ))
        r = Decimal("6.0") / Decimal("1200")
        principal = Decimal("1000000")
        for i, row in enumerate(rows):
            expected = (principal * (ONE + r) ** (i + 1)).quantize(Decimal("0.000001"))
            actual = row.loans[0].balance_close
            assert abs(actual - expected) < Decimal("0.01"), f"Period {i}: expected {expected}, got {actual}"

    def test_no_cash_payment(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="capitalized_interest", active_from=0, active_to=5)],
        ))
        for row in rows:
            assert row.loans[0].interest_paid == ZERO
            assert row.loans[0].principal_paid == ZERO

    def test_ci_does_not_reduce_bank_balance(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="capitalized_interest", active_from=0, active_to=5)],
            opening_cash_balance=Decimal("200000"),
        ))
        # Period 0: draw received, no interest payment
        assert rows[0].bank_balance_close == Decimal("200000") + Decimal("1000000")
        # No drain after that
        for row in rows[1:]:
            assert row.bank_balance_close == rows[0].bank_balance_close

    def test_interest_accrued_field_populated(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="capitalized_interest", rate_pct="6.0", active_from=0, active_to=2)],
        ))
        r = Decimal("6.0") / Decimal("1200")
        principal = Decimal("1000000")
        # Period 0: accrual on initial principal
        assert rows[0].loans[0].interest_accrued == (principal * r).quantize(Decimal("0.000001"))
        # Period 1: accrual on grown balance
        bal_1 = principal * (ONE + r)
        assert rows[1].loans[0].interest_accrued == (bal_1 * r).quantize(Decimal("0.000001"))


# ---------------------------------------------------------------------------
# PI (amortizing) carry
# ---------------------------------------------------------------------------

class TestPICarry:
    def test_balance_declines_to_zero(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(360)],
            loans=[_loan(carry_type="pi", rate_pct="6.0", active_from=0, active_to=359, amort_years=30)],
        ))
        # Balance should be very close to zero at end of amortization
        assert rows[-1].loans[0].balance_close < Decimal("1.00")

    def test_monthly_payment_constant(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(24)],
            loans=[_loan(carry_type="pi", rate_pct="6.0", active_from=0, active_to=23, amort_years=30)],
        ))
        first_pmt = rows[0].loans[0].interest_paid + rows[0].loans[0].principal_paid
        for row in rows:
            detail = row.loans[0]
            pmt = detail.interest_paid + detail.principal_paid
            assert abs(pmt - first_pmt) < Decimal("0.01"), f"Period {row.period}: payment {pmt} != {first_pmt}"

    def test_principal_paid_sum_equals_principal(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(360)],
            loans=[_loan(carry_type="pi", rate_pct="6.0", active_from=0, active_to=359, amort_years=30)],
        ))
        total_principal = sum(row.loans[0].principal_paid for row in rows)
        assert abs(total_principal - Decimal("1000000")) < Decimal("1.00")

    def test_interest_and_principal_decomposition(self):
        # First payment: interest component = P × r
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(2)],
            loans=[_loan(carry_type="pi", rate_pct="6.0", active_from=0, active_to=1, amort_years=30)],
        ))
        r = Decimal("6.0") / Decimal("1200")
        principal = Decimal("1000000")
        expected_interest = (principal * r).quantize(Decimal("0.000001"))
        assert rows[0].loans[0].interest_paid == expected_interest


# ---------------------------------------------------------------------------
# Multi-loan and windowing
# ---------------------------------------------------------------------------

class TestMultiLoanWindowing:
    def test_two_loans_independent_windows(self):
        # Loan A: periods 0-5; Loan B: periods 6-11
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(12)],
            loans=[
                _loan("loan-a", "io_only", "500000", "6.0", active_from=0, active_to=5),
                _loan("loan-b", "io_only", "800000", "7.0", active_from=6, active_to=11),
            ],
        ))
        _q = lambda v: v.quantize(Decimal("0.000001"))
        r_a = _q(Decimal("500000") * Decimal("6") / Decimal("1200"))
        r_b = _q(Decimal("800000") * Decimal("7") / Decimal("1200"))

        for row in rows[:6]:  # A active, B inactive
            details = {d.module_id: d for d in row.loans}
            assert details["loan-a"].interest_paid == r_a
            assert details["loan-b"].interest_paid == ZERO
            assert details["loan-b"].balance_close == ZERO

        for row in rows[6:]:  # B active, A retired
            details = {d.module_id: d for d in row.loans}
            assert details["loan-b"].interest_paid == r_b
            assert details["loan-a"].interest_paid == ZERO
            assert details["loan-a"].balance_close == ZERO

    def test_loan_not_activated_before_from_period(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="io_only", active_from=3, active_to=5)],
        ))
        for row in rows[:3]:  # periods 0-2: inactive
            assert row.loans[0].balance_close == ZERO
            assert row.loans[0].interest_paid == ZERO
            assert row.loans[0].draw_received == ZERO

    def test_loan_draw_only_on_activation_period(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="io_only", active_from=2, active_to=5)],
        ))
        assert rows[2].loans[0].draw_received == Decimal("1000000")
        for row in rows[:2] + rows[3:]:
            assert row.loans[0].draw_received == ZERO


# ---------------------------------------------------------------------------
# Bank balance invariant
# ---------------------------------------------------------------------------

class TestBankBalanceInvariant:
    def test_balance_tracks_inflows_and_outflows(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[_loan(carry_type="io_only", rate_pct="6.0", active_from=0, active_to=5)],
            uses_by_period={0: Decimal("50000"), 1: Decimal("40000"), 2: Decimal("60000")},
            operating_income_by_period={3: Decimal("80000"), 4: Decimal("80000"), 5: Decimal("80000")},
            operating_expenses_by_period={3: Decimal("20000"), 4: Decimal("20000"), 5: Decimal("20000")},
            opening_cash_balance=Decimal("10000"),
        ))
        for row in rows:
            expected_close = (
                row.bank_balance_open
                + sum(d.draw_received for d in row.loans)
                + row.noi
                - row.uses_paid
                - row.total_interest_paid
                - sum(d.principal_paid for d in row.loans)
            ).quantize(Decimal("0.000001"))
            assert row.bank_balance_close == expected_close, f"Period {row.period}: {row.bank_balance_close} != {expected_close}"

    def test_floor_violation_when_balance_below_floor(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="io_only", rate_pct="6.0", active_from=0, active_to=2)],
            uses_by_period={0: Decimal("2000000")},  # massive use drains balance
            reserve_floor_by_period={0: ZERO, 1: Decimal("100000"), 2: Decimal("100000")},
            opening_cash_balance=Decimal("50000"),
        ))
        # Period 1 and 2: balance should be negative → violation
        assert rows[1].floor_violation is True
        assert rows[2].floor_violation is True

    def test_no_violation_when_balance_above_floor(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="io_only", active_from=0, active_to=2)],
            opening_cash_balance=Decimal("5000000"),
            reserve_floor_by_period={m: Decimal("1000") for m in range(3)},
        ))
        assert all(not row.floor_violation for row in rows)

    def test_ir_does_not_count_toward_bank_outflows(self):
        # IR and IO loans side by side; only IO should drain bank balance
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[
                _loan("io", "io_only", "500000", "6.0", 0, 2),
                _loan("ir", "interest_reserve", "500000", "6.0", 0, 2),
            ],
            opening_cash_balance=Decimal("100000"),
        ))
        io_interest = Decimal("500000") * Decimal("6") / Decimal("1200")
        # Period 0: draw IO(500k) + IR(500k) = +1M; pay IO interest = -io_interest; IR pool only
        expected_0 = Decimal("100000") + Decimal("500000") + Decimal("500000") - io_interest
        assert abs(rows[0].bank_balance_close - expected_0.quantize(Decimal("0.000001"))) < Decimal("0.01")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_rate_io(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="io_only", rate_pct="0.0", active_from=0, active_to=2)],
        ))
        for row in rows:
            assert row.loans[0].interest_paid == ZERO

    def test_zero_rate_ci(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(3)],
            loans=[_loan(carry_type="capitalized_interest", rate_pct="0.0", active_from=0, active_to=2)],
        ))
        for row in rows:
            assert row.loans[0].interest_accrued == ZERO

    def test_no_loans(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6)],
            loans=[],
            opening_cash_balance=Decimal("100000"),
        ))
        assert len(rows) == 6
        for row in rows:
            assert row.bank_balance_close == Decimal("100000")

    def test_single_period(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(1)],
            loans=[_loan(carry_type="io_only", active_from=0, active_to=0)],
        ))
        assert len(rows) == 1
        assert rows[0].loans[0].draw_received == Decimal("1000000")

    def test_period_count_matches_sum_of_phase_months(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(6, "construction"), _phase(3, "lease_up"), _phase(12, "stabilized")],
            loans=[],
        ))
        assert len(rows) == 21

    def test_period_types_assigned_correctly(self):
        rows = run_period_engine(PeriodEngineInputs(
            phases=[_phase(2, "construction"), _phase(2, "lease_up"), _phase(2, "stabilized")],
            loans=[],
        ))
        types = [r.period_type for r in rows]
        assert types == ["construction", "construction", "lease_up", "lease_up", "stabilized", "stabilized"]
