"""Wiring tests for the bank-account proof inside cashflow.py.

Exercises `_run_bank_account_proof` directly with hand-crafted phases +
CashFlow rows + UseLines. Verifies the helper returns the expected proof
summary or None for the degenerate inputs.
"""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.engines.cashflow import (
    _CASH_FLOW_SUPPORT_RESERVE_LABEL,
    _bank_account_reserve_active_for,
    _run_bank_account_proof,
    _upsert_cash_flow_support_reserve,
)
import app.engines.cashflow as _cashflow_mod
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


class _StubSession:
    """Minimal AsyncSession stand-in. Tracks add/delete calls; no real DB."""
    def __init__(self) -> None:
        self.added: list = []
        self.deleted: list = []
    def add(self, obj) -> None:
        self.added.append(obj)
    def delete(self, obj) -> None:
        self.deleted.append(obj)


def _proof_stub(max_shortfall: str, date: str = "2026-08-01") -> dict:
    return {"max_shortfall": max_shortfall, "max_shortfall_date": date}


import uuid


@pytest.mark.unit
@pytest.mark.unit
def test_reserve_gate_global_flag_off_is_inactive(monkeypatch):
    """Global flag off, allowlist empty → feature OFF for every scenario."""
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ENABLED", False)
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ALLOWLIST", set())
    assert _bank_account_reserve_active_for("any-scenario-id") is False
    assert _bank_account_reserve_active_for(None) is False


@pytest.mark.unit
def test_reserve_gate_global_flag_on_is_active(monkeypatch):
    """Global flag on, allowlist empty → feature ON for every scenario."""
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ENABLED", True)
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ALLOWLIST", set())
    assert _bank_account_reserve_active_for("any-scenario-id") is True


@pytest.mark.unit
def test_reserve_gate_allowlist_restricts_to_listed_scenarios(monkeypatch):
    """Allowlist non-empty → only listed scenarios are active, even when the
    global flag is OFF. Lets us pilot the feature on one test deal."""
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ENABLED", False)
    monkeypatch.setattr(
        _cashflow_mod,
        "_BANK_ACCOUNT_RESERVE_ALLOWLIST",
        {"cf0e77c3-a445-434c-8788-6d948303d916"},
    )
    # Allowed scenario → active
    assert _bank_account_reserve_active_for(
        "cf0e77c3-a445-434c-8788-6d948303d916"
    ) is True
    # Case-insensitive match
    assert _bank_account_reserve_active_for(
        "CF0E77C3-A445-434C-8788-6D948303D916"
    ) is True
    # Other scenario → inactive
    assert _bank_account_reserve_active_for(
        "11111111-2222-3333-4444-555555555555"
    ) is False
    # None → inactive
    assert _bank_account_reserve_active_for(None) is False


@pytest.mark.unit
def test_reserve_gate_allowlist_overrides_global_flag(monkeypatch):
    """When the allowlist is set, the global flag is ignored — only listed
    scenarios are active even if the global flag was ON."""
    monkeypatch.setattr(_cashflow_mod, "_BANK_ACCOUNT_RESERVE_ENABLED", True)
    monkeypatch.setattr(
        _cashflow_mod,
        "_BANK_ACCOUNT_RESERVE_ALLOWLIST",
        {"only-this-scenario"},
    )
    assert _bank_account_reserve_active_for("only-this-scenario") is True
    assert _bank_account_reserve_active_for("any-other-scenario") is False


def test_upsert_creates_new_use_line_when_gap_positive():
    sess = _StubSession()
    use_lines: list = []
    pid = uuid.uuid4()
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=pid,
        use_lines=use_lines,
        amount=Decimal("75_000"),
        proof_result=_proof_stub("75000"),
    )
    assert action == "created"
    assert len(use_lines) == 1
    ul = use_lines[0]
    assert ul.label == _CASH_FLOW_SUPPORT_RESERVE_LABEL
    assert ul.amount == Decimal("75_000")
    assert ul.timing_type == "first_day"
    assert ul.cost_category == "soft"
    assert ul.project_id == pid
    assert ul in sess.added


@pytest.mark.unit
def test_upsert_updates_existing_when_amount_changes():
    # Use a real UseLine instance to exercise attribute assignment
    from app.models.deal import UseLine
    pid = uuid.uuid4()
    existing = UseLine(
        project_id=pid,
        label=_CASH_FLOW_SUPPORT_RESERVE_LABEL,
        amount=Decimal("50_000"),
        timing_type="first_day",
        cost_category="soft",
    )
    sess = _StubSession()
    use_lines: list = [existing]
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=pid,
        use_lines=use_lines,
        amount=Decimal("90_000"),
        proof_result=_proof_stub("90000"),
    )
    assert action == "updated"
    assert existing.amount == Decimal("90_000")
    assert len(use_lines) == 1


@pytest.mark.unit
def test_upsert_unchanged_when_amount_matches():
    from app.models.deal import UseLine
    pid = uuid.uuid4()
    existing = UseLine(
        project_id=pid,
        label=_CASH_FLOW_SUPPORT_RESERVE_LABEL,
        amount=Decimal("100_000"),
        timing_type="first_day",
        cost_category="soft",
    )
    sess = _StubSession()
    use_lines = [existing]
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=pid,
        use_lines=use_lines,
        amount=Decimal("100_000"),
        proof_result=_proof_stub("100000"),
    )
    assert action == "unchanged"
    assert sess.added == []
    assert sess.deleted == []


@pytest.mark.unit
def test_upsert_removes_existing_when_gap_zero():
    from app.models.deal import UseLine
    pid = uuid.uuid4()
    existing = UseLine(
        project_id=pid,
        label=_CASH_FLOW_SUPPORT_RESERVE_LABEL,
        amount=Decimal("75_000"),
        timing_type="first_day",
        cost_category="soft",
    )
    sess = _StubSession()
    use_lines = [existing]
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=pid,
        use_lines=use_lines,
        amount=Decimal("0"),
        proof_result=_proof_stub("0"),
    )
    assert action == "removed"
    assert use_lines == []
    assert existing in sess.deleted


@pytest.mark.unit
def test_upsert_unchanged_when_gap_zero_and_no_existing():
    sess = _StubSession()
    use_lines: list = []
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=uuid.uuid4(),
        use_lines=use_lines,
        amount=Decimal("0"),
        proof_result=_proof_stub("0"),
    )
    assert action == "unchanged"
    assert use_lines == []
    assert sess.added == []


@pytest.mark.unit
def test_upsert_no_project_id_skips_create():
    """Engine-emitted reserves need a project FK. No project = no create."""
    sess = _StubSession()
    use_lines: list = []
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=None,
        use_lines=use_lines,
        amount=Decimal("50_000"),
        proof_result=_proof_stub("50000"),
    )
    assert action == "unchanged"
    assert use_lines == []


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
def test_stress_deal_emits_cash_flow_support_and_converges_to_solvent():
    """End-to-end stress: realistic underfunded lease-up triggers shortfall,
    upsert emits a Cash Flow Support Reserve sized to plug it, the
    re-proof with the augmented use_lines is solvent. Proves the full
    detect → emit → converge loop the /compute iteration relies on.

    Stress profile (mirrors a tight value-add deal):
      - 6-month lease-up with $30K/mo perm DS plus $8K/mo OpEx
      - Income ramps 0 → $40K (S-curve floor) over the window
      - Existing reserves: OR=$60K, LUR=$40K → opening cash $100K, $60K floor
      - Each month net negative until month 4 → bank drops below floor
    """
    phases = [
        PhaseSpec(PeriodType.lease_up, 6),
        PhaseSpec(PeriodType.stabilized, 12),
    ]
    rows = [
        _Row(period=0, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("0"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=1, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("8_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=2, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("16_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=3, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("24_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=4, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("32_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=5, period_type=PeriodType.lease_up,
             effective_gross_income=Decimal("40_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
        _Row(period=6, period_type=PeriodType.stabilized,
             effective_gross_income=Decimal("48_000"),
             operating_expenses=Decimal("8_000"),
             debt_service=Decimal("30_000")),
    ]
    use_lines: list = [
        _UL("Operating Reserve", Decimal("60_000")),
        _UL("Lease-Up Reserve",  Decimal("40_000")),
    ]

    # Step 1 — proof under stress: expect shortfall
    proof1 = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert proof1 is not None
    assert proof1["is_solvent"] is False
    gap = Decimal(proof1["max_shortfall"])
    assert gap > Decimal("0")

    # Step 2 — auto-emit Cash Flow Support Reserve sized to the gap
    sess = _StubSession()
    pid = uuid.uuid4()
    action = _upsert_cash_flow_support_reserve(
        session=sess,
        project_id=pid,
        use_lines=use_lines,
        amount=gap,
        proof_result=proof1,
    )
    assert action == "created"
    cfs = next(ul for ul in use_lines
               if getattr(ul, "label", "") == _CASH_FLOW_SUPPORT_RESERVE_LABEL)
    assert cfs.amount == gap
    assert cfs.timing_type == "first_day"
    assert cfs.cost_category == "soft"
    assert cfs.project_id == pid

    # Step 3 — re-run proof with augmented use_lines → solvent (convergence)
    proof2 = _run_bank_account_proof(
        cash_flow_rows=rows,
        use_lines=use_lines,
        phases=phases,
        milestone_dates={"acquisition_start": "2026-01-01"},
    )
    assert proof2 is not None
    assert proof2["is_solvent"] is True
    assert Decimal(proof2["max_shortfall"]) == Decimal("0")


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
