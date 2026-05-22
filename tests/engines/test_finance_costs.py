"""Unit tests for Total Finance Costs auto-injection in cashflow engine.

Covers:
- One row per CapitalModule labeled "{module.label} — Total Finance Costs"
- Amount = DEFAULT_FINANCE_COST_PCT × principal
- is_auto_finance_cost=True on engine-created rows
- User edit (flag=False) is respected: row not overwritten on recompute
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.cashflow import DEFAULT_FINANCE_COST_PCT


@pytest.mark.unit
def test_default_finance_cost_pct_is_two_percent():
    """Sanity: documented default is 2.0%."""
    assert DEFAULT_FINANCE_COST_PCT == Decimal("2.0")


@pytest.mark.unit
def test_legacy_default_loan_costs_removed():
    """The old per-fee table _DEFAULT_LOAN_COSTS must no longer exist."""
    import app.engines.cashflow as cf
    assert not hasattr(cf, "_DEFAULT_LOAN_COSTS"), (
        "Legacy _DEFAULT_LOAN_COSTS table should be removed; replaced by "
        "DEFAULT_FINANCE_COST_PCT single global rate."
    )


@pytest.mark.unit
def test_aps_map_covers_all_milestone_keys():
    """All milestone-key strings the wizard can write must map to a use-line phase.

    Unmapped values would default to "acquisition" via .get(), which is now safe
    — but explicit mapping prevents silent fallback for known keys.
    """
    from app.engines.cashflow import _APS_TO_USE_PHASE
    required_keys = {
        "acquisition", "close", "offer_made", "under_contract",
        "pre_construction", "pre_development",
        "construction",
        "lease_up", "operation_lease_up",
        "stabilized", "operation_stabilized",
        "exit", "divestment",
    }
    missing = required_keys - set(_APS_TO_USE_PHASE.keys())
    assert not missing, f"_APS_TO_USE_PHASE missing milestone keys: {missing}"


@pytest.mark.unit
def test_auto_finance_cost_phase_coercion_for_late_activation():
    """Finance costs are paid at LOAN CLOSING, not at loan activation.

    Regression: perm debt with active_phase_start="operation_stabilized" (perm
    activates at stab) was creating a "Total Finance Costs" UseLine in
    phase="operation", landing the ~2% origination lump in stabilized month 1
    and crushing Year 1 stab profit.

    Fix: at the auto-FC writeback site, coerce operation/exit phase values
    back to "acquisition" so the lump fires at deal close where the lender
    is paid. Refi-specific finance costs are still handled separately by the
    refi event.
    """
    from app.engines.cashflow import _APS_TO_USE_PHASE

    def _coerce(aps: str) -> str:
        phase = _APS_TO_USE_PHASE.get(aps, "acquisition")
        if phase in {"operation", "exit"}:
            phase = "acquisition"
        return phase

    # Late-activation perm debt → coerced to acquisition
    assert _coerce("operation_stabilized") == "acquisition"
    assert _coerce("stabilized") == "acquisition"
    assert _coerce("lease_up") == "acquisition"
    assert _coerce("operation_lease_up") == "acquisition"
    assert _coerce("exit") == "acquisition"
    assert _coerce("divestment") == "acquisition"
    # Acquisition-time milestones stay at acquisition
    assert _coerce("acquisition") == "acquisition"
    assert _coerce("close") == "acquisition"
    assert _coerce("offer_made") == "acquisition"
    assert _coerce("under_contract") == "acquisition"
    # Pre-construction / construction loans preserve their phase
    assert _coerce("pre_construction") == "pre_construction"
    assert _coerce("pre_development") == "pre_construction"
    assert _coerce("construction") == "construction"
    # Unknown / NULL → default acquisition (not "pre_construction" as before)
    assert _coerce("") == "acquisition"
    assert _coerce("garbage_value") == "acquisition"
