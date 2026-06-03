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
from app.models.cashflow import OperationalOutputs, PeriodType


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
def test_proof_acquisition_only_runs_short_stabilized_window():
    """Acquisition deals (no lease_up) get a short stabilized window proof.

    The proof anchors at the stabilization start and covers
    _ACQUISITION_PROOF_MONTHS to verify that OR + perm DS + stabilized OpEx
    balance for the first months after close.
    """
    phases = [
        PhaseSpec(PeriodType.acquisition, 1),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    rows = [_Row(period=0, period_type=PeriodType.acquisition)]
    rows.extend([
        _Row(period=i, period_type=PeriodType.stabilized,
             effective_gross_income=Decimal("15_000"),
             operating_expenses=Decimal("5_000"),
             debt_service=Decimal("8_000"))
        for i in range(1, 13)
    ])
    use_lines = [
        _UL("Operating Reserve", Decimal("50_000")),
    ]
    result = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert result is not None, "acquisition deal should produce a proof"
    assert result["is_solvent"] is True
    assert result["max_shortfall"] == "0"
    # Window starts at stab_period and runs _ACQUISITION_PROOF_MONTHS rows.
    assert result["proof_start"] == "stabilized"
    assert result["co_period"] == result["stabilized_period"] == 1
    assert result["months_simulated"] == 3


# CFSR upsert helper, gate-flag plumbing, and the stress
# detect → emit → converge loop were removed in Slice 5b of
# reserves-spec-align. The bank-account proof itself remains, demoted
# to validation only — the Operating Deficit Reserve (Slice 4) is now
# the engine's first-class home for the operating shortfall, and the
# Stabilization-anchor validator (Slice 5d) catches the misconfiguration
# the old proof-driven CFSR was masking.


import uuid                                                  # noqa: E402


@pytest.mark.unit
def test_operational_outputs_carries_bank_account_proof_column():
    """OperationalOutputs ORM model exposes bank_account_proof field."""
    # Instantiate with the column set — ensures the SQLAlchemy mapping
    # accepts the new JSON column added in migration 0102.
    out = OperationalOutputs(
        scenario_id=uuid.uuid4(),
        bank_account_proof={"is_solvent": True, "max_shortfall": "0"},
    )
    assert out.bank_account_proof == {"is_solvent": True, "max_shortfall": "0"}
    # Defaults to None when omitted
    out2 = OperationalOutputs(scenario_id=uuid.uuid4())
    assert out2.bank_account_proof is None


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


@pytest.mark.unit
def test_proof_with_dev_fee_paydowns_grows_shortfall():
    """Wiring: a non-empty `dev_fee_paydowns_by_period` must propagate through
    `_run_bank_account_proof` to the extractor and inflate outflows so the
    sized shortfall exceeds the no-paydown baseline."""
    phases = [
        PhaseSpec(PeriodType.lease_up, 3),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    rows = [
        _Row(period=0, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("20_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
        _Row(period=1, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("20_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
        _Row(period=2, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("20_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000")),
    ]
    use_lines = [_UL("Operating Reserve", Decimal("5_000"))]  # tight floor

    baseline = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    with_paydowns = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
        dev_fee_paydowns_by_period={0: Decimal("4_000"), 1: Decimal("4_000")},
    )
    assert baseline is not None and with_paydowns is not None
    # Baseline NCF per row = 20K - 8K - 10K = +2K → opening 5K + 2K = 7K above floor.
    assert baseline["is_solvent"] is True
    # With 4K/mo paydown, NCF = -2K → 5K - 2K - 2K = 1K → 4K below 5K floor.
    assert with_paydowns["is_solvent"] is False
    assert Decimal(with_paydowns["max_shortfall"]) > Decimal(baseline["max_shortfall"])


@pytest.mark.unit
def test_proof_paydowns_none_matches_legacy_behavior():
    """Wiring sanity: paydowns kwarg defaults to None and produces the same
    proof a legacy caller without the kwarg would have produced."""
    phases = [
        PhaseSpec(PeriodType.lease_up, 3),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    rows = [
        _Row(period=i, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("20_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("10_000"))
        for i in range(3)
    ]
    use_lines = [_UL("Operating Reserve", Decimal("100_000"))]
    legacy = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    explicit_none = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
        dev_fee_paydowns_by_period=None,
    )
    empty_dict = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
        dev_fee_paydowns_by_period={},
    )
    assert legacy == explicit_none == empty_dict


@pytest.mark.unit
def test_is_stream_active_distinguishes_lease_up_ramp_from_stabilized_only():
    """LUR sizing gates the 1/3 NOI offset on whether any income stream
    is active during lease-up. Streams gated to `stabilized` (or later)
    must not credit the offset — otherwise LUR collapses to zero and
    perm DS during lease-up goes uncovered. This was the root cause of
    the 5 production deals with bank-account shortfalls on 2026-06-01.
    """
    from app.engines.cashflow_compile import _is_stream_active
    from app.models.cashflow import PeriodType

    class _Stream:
        def __init__(self, phases):
            self.active_in_phases = phases

    stabilized_only = _Stream(["stabilized"])
    ramps_in_lease_up = _Stream(["lease_up", "stabilized"])

    # Stabilized-only streams do NOT contribute to lease-up income —
    # the LUR sizer must zero its income offset in this case.
    assert _is_stream_active(stabilized_only, PeriodType.lease_up) is False
    # Streams that explicitly include lease_up DO ramp — offset applies.
    assert _is_stream_active(ramps_in_lease_up, PeriodType.lease_up) is True
