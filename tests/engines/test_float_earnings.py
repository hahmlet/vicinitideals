"""Unit tests for the float-earnings engine module.

Covers the closed-form balance schedule math, the split allocator, the
compute-time validation gate, and the top-level scenario orchestrator.
Pure-Python — no DB fixtures required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.engines.float_earnings import (
    FloatBalanceRow,
    FloatEarningsResult,
    FloatValidation,
    compute_balance_schedule,
    compute_scenario_float_earnings,
    split_earnings,
    validate_float_source,
)

ZERO = Decimal("0")
PENNY = Decimal("0.01")


def _module(
    *,
    id: UUID | None = None,
    label: str = "Module",
    vehicle_type: str = "debt",
    source: dict | None = None,
    carry: dict | None = None,
) -> SimpleNamespace:
    """Build a CapitalModule stand-in for tests."""
    return SimpleNamespace(
        id=id or uuid4(),
        label=label,
        vehicle_type=vehicle_type,
        source=source or {},
        carry=carry or {},
    )


def _milestone(*, id: UUID | None = None, milestone_type: str = "construction") -> SimpleNamespace:
    return SimpleNamespace(id=id or uuid4(), milestone_type=milestone_type)


# ---------------------------------------------------------------------------
# compute_balance_schedule — closed-form math
# ---------------------------------------------------------------------------

class TestBalanceSchedule:
    def test_zero_principal_returns_empty(self):
        total, schedule = compute_balance_schedule(
            parent_principal=ZERO,
            construction_months=10,
            yield_pct=Decimal("5"),
        )
        assert total == ZERO
        assert schedule == []

    def test_zero_yield_returns_empty(self):
        total, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=10,
            yield_pct=ZERO,
        )
        assert total == ZERO
        assert schedule == []

    def test_zero_months_returns_empty(self):
        total, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=0,
            yield_pct=Decimal("5"),
        )
        assert total == ZERO
        assert schedule == []

    def test_schedule_length_matches_construction_months(self):
        _, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=12,
            yield_pct=Decimal("4.30"),
        )
        assert len(schedule) == 12
        assert schedule[0].period == 1
        assert schedule[-1].period == 12

    def test_opening_balance_starts_at_principal(self):
        principal = Decimal("10000000")
        _, schedule = compute_balance_schedule(
            parent_principal=principal,
            construction_months=10,
            yield_pct=Decimal("5"),
        )
        assert schedule[0].opening_balance == principal

    def test_closing_balance_depletes_to_zero(self):
        _, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=10,
            yield_pct=Decimal("5"),
        )
        # Final month's closing balance reflects linear depletion to zero
        # (within Decimal quantization tolerance).
        assert schedule[-1].closing_balance < Decimal("1")

    def test_closed_form_total_matches_hand_calc(self):
        """Closed-form: total = P × y/100/12 × (N+1)/2.

        $10M at 5% annual yield, 10-month construction:
            monthly_rate = 5/100/12 = 0.004166...
            average opening balance over 10 months = 10M × (10+1)/2/10
                                                   = 10M × 0.55
                                                   = 5,500,000
            total = 5,500,000 × 0.004166... = ~22,916.66...
            But the formula sums opening balances directly:
            sum = 10M + 9M + 8M + ... + 1M = 55M
            earnings = 55M × 0.004166... = 229,166.66...
        """
        total, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=10,
            yield_pct=Decimal("5"),
        )
        # Hand calc: sum of openings = 10M+9M+...+1M = 55M; × 5/100/12 = 229,166.67
        expected = Decimal("229166.666667")
        assert abs(total - expected) < PENNY

    def test_monthly_earnings_decreases_as_balance_depletes(self):
        _, schedule = compute_balance_schedule(
            parent_principal=Decimal("10000000"),
            construction_months=10,
            yield_pct=Decimal("5"),
        )
        # Each successive month should earn less (balance depletes)
        for i in range(len(schedule) - 1):
            assert schedule[i].monthly_earnings > schedule[i + 1].monthly_earnings


# ---------------------------------------------------------------------------
# split_earnings — allocation between dev fee + debt paydown
# ---------------------------------------------------------------------------

class TestSplitEarnings:
    def test_default_to_paydown_when_both_zero(self):
        dev, paydown = split_earnings(
            total=Decimal("1000"),
            dev_fee_split_pct=ZERO,
            debt_paydown_split_pct=ZERO,
        )
        assert dev == ZERO
        assert paydown == Decimal("1000")

    def test_full_paydown(self):
        dev, paydown = split_earnings(
            total=Decimal("1000"),
            dev_fee_split_pct=ZERO,
            debt_paydown_split_pct=Decimal("100"),
        )
        assert dev == ZERO
        assert paydown == Decimal("1000")

    def test_full_dev_fee(self):
        dev, paydown = split_earnings(
            total=Decimal("1000"),
            dev_fee_split_pct=Decimal("100"),
            debt_paydown_split_pct=ZERO,
        )
        assert dev == Decimal("1000")
        assert paydown == ZERO

    def test_fifty_fifty(self):
        dev, paydown = split_earnings(
            total=Decimal("1000"),
            dev_fee_split_pct=Decimal("50"),
            debt_paydown_split_pct=Decimal("50"),
        )
        assert dev == Decimal("500")
        assert paydown == Decimal("500")

    def test_split_sums_to_total(self):
        """Dev + paydown must always sum to total to avoid silent dollar loss."""
        dev, paydown = split_earnings(
            total=Decimal("1234.56"),
            dev_fee_split_pct=Decimal("33"),
            debt_paydown_split_pct=Decimal("67"),
        )
        assert dev + paydown == Decimal("1234.56")

    def test_none_splits_treated_as_zero(self):
        dev, paydown = split_earnings(
            total=Decimal("1000"),
            dev_fee_split_pct=None,  # type: ignore[arg-type]
            debt_paydown_split_pct=None,  # type: ignore[arg-type]
        )
        assert dev == ZERO
        assert paydown == Decimal("1000")


# ---------------------------------------------------------------------------
# validate_float_source — compute-time precondition checks
# ---------------------------------------------------------------------------

class TestValidateFloatSource:
    def test_missing_parent_blocks_earnings(self):
        float_mod = _module(
            vehicle_type="float_earnings",
            label="Bond Float",
            source={},
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[float_mod],
            milestones=[],
        )
        assert v.earnings_blocked is True
        assert v.paydown_blocked is True
        assert any("no parent" in w for w in v.warnings)

    def test_deleted_parent_blocks_earnings(self):
        float_mod = _module(
            vehicle_type="float_earnings",
            source={"parent_module_id": str(uuid4())},
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[float_mod],
            milestones=[],
        )
        assert v.earnings_blocked is True
        assert any("no longer exists" in w for w in v.warnings)

    def test_parent_wrong_draw_type_blocks_earnings(self):
        parent = _module(
            vehicle_type="debt",
            label="RJ Bond",
            source={"draw_type": "draw_down", "balance_earns_interest": True},
        )
        float_mod = _module(
            vehicle_type="float_earnings",
            source={"parent_module_id": str(parent.id)},
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[parent, float_mod],
            milestones=[],
        )
        assert v.earnings_blocked is True
        assert any("draws at start" in w for w in v.warnings)

    def test_parent_flag_off_blocks_earnings(self):
        parent = _module(
            vehicle_type="debt",
            label="RJ Bond",
            source={"draw_type": "fully_drawn", "balance_earns_interest": False},
        )
        float_mod = _module(
            vehicle_type="float_earnings",
            source={"parent_module_id": str(parent.id)},
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[parent, float_mod],
            milestones=[],
        )
        assert v.earnings_blocked is True
        assert any("Balance Earns Interest" in w for w in v.warnings)

    def test_happy_path_paydown_only(self):
        debt_target = _module(vehicle_type="debt", label="RJ Bond")
        parent = _module(
            vehicle_type="debt",
            label="RJ Bond",
            source={"draw_type": "fully_drawn", "balance_earns_interest": True},
        )
        ms = _milestone()
        float_mod = _module(
            vehicle_type="float_earnings",
            source={
                "parent_module_id": str(parent.id),
                "debt_paydown_split_pct": "100",
                "paydown_debt_module_id": str(debt_target.id),
                "paydown_milestone_id": str(ms.id),
            },
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[parent, debt_target, float_mod],
            milestones=[ms],
        )
        assert v.earnings_blocked is False
        assert v.paydown_blocked is False
        assert v.warnings == []

    def test_deleted_paydown_target_blocks_paydown_only(self):
        parent = _module(
            vehicle_type="debt",
            source={"draw_type": "fully_drawn", "balance_earns_interest": True},
        )
        ms = _milestone()
        float_mod = _module(
            vehicle_type="float_earnings",
            source={
                "parent_module_id": str(parent.id),
                "debt_paydown_split_pct": "100",
                "paydown_debt_module_id": str(uuid4()),  # non-existent
                "paydown_milestone_id": str(ms.id),
            },
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[parent, float_mod],
            milestones=[ms],
        )
        assert v.earnings_blocked is False  # earnings still computable
        assert v.paydown_blocked is True
        assert any("debt module deleted" in w for w in v.warnings)

    def test_deleted_milestone_blocks_paydown_only(self):
        parent = _module(
            vehicle_type="debt",
            source={"draw_type": "fully_drawn", "balance_earns_interest": True},
        )
        debt_target = _module(vehicle_type="debt")
        float_mod = _module(
            vehicle_type="float_earnings",
            source={
                "parent_module_id": str(parent.id),
                "debt_paydown_split_pct": "100",
                "paydown_debt_module_id": str(debt_target.id),
                "paydown_milestone_id": str(uuid4()),  # non-existent
            },
        )
        v = validate_float_source(
            float_module=float_mod,
            capital_modules=[parent, debt_target, float_mod],
            milestones=[],
        )
        assert v.earnings_blocked is False
        assert v.paydown_blocked is True
        assert any("milestone deleted" in w for w in v.warnings)


# ---------------------------------------------------------------------------
# compute_scenario_float_earnings — top-level orchestrator
# ---------------------------------------------------------------------------

class TestComputeScenario:
    def test_no_float_sources_returns_empty(self):
        results = compute_scenario_float_earnings(
            capital_modules=[_module(vehicle_type="debt"), _module(vehicle_type="equity")],
            milestones=[],
            construction_months=10,
        )
        assert results == []

    def test_happy_path_produces_earnings_and_paydown(self):
        parent = _module(
            vehicle_type="debt",
            label="RJ Bond",
            source={
                "amount": "10000000",
                "draw_type": "fully_drawn",
                "balance_earns_interest": True,
            },
        )
        debt_target = _module(vehicle_type="debt", label="RJ Bond", id=parent.id)
        ms = _milestone()
        float_mod = _module(
            vehicle_type="float_earnings",
            label="Bond Float",
            source={
                "parent_module_id": str(parent.id),
                "yield_pct": "5",
                "debt_paydown_split_pct": "100",
                "dev_fee_split_pct": "0",
                "paydown_debt_module_id": str(debt_target.id),
                "paydown_milestone_id": str(ms.id),
            },
        )
        results = compute_scenario_float_earnings(
            capital_modules=[parent, float_mod],
            milestones=[ms],
            construction_months=10,
        )
        assert len(results) == 1
        r = results[0]
        assert r.warnings == []
        # Closed-form: $10M × 5/100/12 × sum(1..10/10) = $10M × 0.004166 × 5.5 = $229,166.67
        assert abs(r.total_earnings - Decimal("229166.666667")) < PENNY
        assert r.paydown_amount == r.total_earnings
        assert r.dev_fee_topup_amount == ZERO
        assert r.parent_module_id == parent.id

    def test_blocked_source_produces_zero_with_warnings(self):
        float_mod = _module(
            vehicle_type="float_earnings",
            label="Orphan Float",
            source={},  # no parent
        )
        results = compute_scenario_float_earnings(
            capital_modules=[float_mod],
            milestones=[],
            construction_months=10,
        )
        assert len(results) == 1
        assert results[0].total_earnings == ZERO
        assert results[0].paydown_amount == ZERO
        assert any("no parent" in w for w in results[0].warnings)

    def test_paydown_blocked_zeros_paydown_keeps_earnings(self):
        parent = _module(
            vehicle_type="debt",
            source={
                "amount": "10000000",
                "draw_type": "fully_drawn",
                "balance_earns_interest": True,
            },
        )
        float_mod = _module(
            vehicle_type="float_earnings",
            source={
                "parent_module_id": str(parent.id),
                "yield_pct": "5",
                "debt_paydown_split_pct": "100",
                # Missing paydown_debt_module_id + paydown_milestone_id
            },
        )
        results = compute_scenario_float_earnings(
            capital_modules=[parent, float_mod],
            milestones=[],
            construction_months=10,
        )
        r = results[0]
        # Earnings computed normally
        assert r.total_earnings > ZERO
        # But paydown zeroed because FKs missing
        assert r.paydown_amount == ZERO
        assert r.paydown_debt_module_id is None
        assert r.paydown_milestone_id is None
        assert any("paydown skipped" in w for w in r.warnings)

    def test_split_5050(self):
        parent = _module(
            vehicle_type="debt",
            source={
                "amount": "10000000",
                "draw_type": "fully_drawn",
                "balance_earns_interest": True,
            },
        )
        debt_target = _module(vehicle_type="debt")
        ms = _milestone()
        float_mod = _module(
            vehicle_type="float_earnings",
            source={
                "parent_module_id": str(parent.id),
                "yield_pct": "5",
                "dev_fee_split_pct": "50",
                "debt_paydown_split_pct": "50",
                "paydown_debt_module_id": str(debt_target.id),
                "paydown_milestone_id": str(ms.id),
            },
        )
        results = compute_scenario_float_earnings(
            capital_modules=[parent, debt_target, float_mod],
            milestones=[ms],
            construction_months=10,
        )
        r = results[0]
        # Sum of split halves equals total
        assert r.dev_fee_topup_amount + r.paydown_amount == r.total_earnings
        # Half-and-half (modulo penny rounding)
        assert abs(r.dev_fee_topup_amount - r.paydown_amount) < PENNY
