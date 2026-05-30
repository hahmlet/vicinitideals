"""Wiring tests for the bank-account proof inside cashflow.py.

Exercises `_run_bank_account_proof` directly with hand-crafted phases +
CashFlow rows + UseLines. Verifies the helper returns the expected proof
summary or None for the degenerate inputs.
"""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.engines.cashflow import _run_bank_account_proof
from app.engines.cashflow_compile import PhaseSpec
from app.models.cashflow import PeriodType


@dataclass
class _Row:
    period: int
    period_type: PeriodType
    effective_gross_income: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    debt_service: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")


@dataclass
class _UL:
    label: str
    amount: Decimal
    timing_type: str = "first_day"


@pytest.mark.unit
def test_proof_returns_none_when_no_operating_phase():
    """Construction-only phase plan should yield no proof window."""
    phases = [
        PhaseSpec(PeriodType.acquisition, 1),
        PhaseSpec(PeriodType.construction, 12),
    ]
    rows = [
        _Row(period=0, period_type=PeriodType.acquisition),
        _Row(period=1, period_type=PeriodType.construction),
    ]
    result = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=[],
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert result is None


@pytest.mark.unit
def test_proof_returns_none_when_no_anchor_date():
    phases = [
        PhaseSpec(PeriodType.lease_up, 3),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    rows = [_Row(period=0, period_type=PeriodType.lease_up)]
    result = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=[],
        phases=phases,
        milestone_dates=None,
    )
    assert result is None


@pytest.mark.unit
def test_proof_solvent_when_reserves_cover_window():
    """Healthy deal: opening reserves >> outflows during lease-up."""
    phases = [
        PhaseSpec(PeriodType.acquisition, 1),
        PhaseSpec(PeriodType.construction, 12),
        PhaseSpec(PeriodType.lease_up, 3),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    # 13 construction rows produce nothing; rows 13/14/15 = lease_up
    rows = [
        _Row(period=i, period_type=PeriodType.construction) for i in range(13)
    ]
    rows.extend([
        _Row(period=13, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("20_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
        _Row(period=14, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("30_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
        _Row(period=15, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("40_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
    ])
    use_lines = [
        _UL("Operating Reserve", Decimal("100_000")),
        _UL("Lease-Up Reserve",  Decimal("100_000")),
    ]
    result = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert result is not None
    assert result["is_solvent"] is True
    assert result["max_shortfall"] == "0"
    assert result["co_period"] == 13
    assert result["stabilized_period"] == 16
    assert result["months_simulated"] == 3


@pytest.mark.unit
def test_proof_surfaces_shortfall_when_underfunded():
    """Tight lease-up: small OR, big perm DS → proof fails."""
    phases = [
        PhaseSpec(PeriodType.lease_up, 3),
        PhaseSpec(PeriodType.stabilized, 1),
    ]
    rows = [
        _Row(period=0, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("0"),
             operating_expenses=Decimal("5_000"),
             debt_service=Decimal("30_000")),
        _Row(period=1, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("5_000"),
             operating_expenses=Decimal("5_000"),
             debt_service=Decimal("30_000")),
        _Row(period=2, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("10_000"),
             operating_expenses=Decimal("5_000"),
             debt_service=Decimal("30_000")),
        _Row(period=3, period_type=PeriodType.stabilized,
             effective_gross_income=Decimal("50_000"),
             operating_expenses=Decimal("5_000"),
             debt_service=Decimal("30_000")),
    ]
    use_lines = [
        _UL("Operating Reserve", Decimal("50_000")),  # floor
        _UL("Lease-Up Reserve",  Decimal("30_000")),  # opening pool
    ]
    result = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert result is not None
    assert result["is_solvent"] is False
    # opening = 80K. Month 0 net -35K → 45K. Month 1 net -30K → 15K (below 50K floor by 35K).
    # Month 2 net -25K → -10K (below floor by 60K). Stab not in window.
    assert Decimal(result["max_shortfall"]) > Decimal("0")
    # Stabilized period is the boundary; only lease-up rows simulated
    assert result["months_simulated"] == 3
