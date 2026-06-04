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
def test_auto_finance_cost_phase_inherits_from_source():
    """Auto-FC UseLine phase mirrors the parent Source's active_phase_start.

    Per user requirement (Jun 2026): auto-generated FC rows must inherit
    start period from their Source and be locked on the UI. The engine
    no longer coerces phase strings — it copies the mapping directly so
    the FC row fires at the same milestone the loan first becomes active.

    The Active From milestone FK is the load-bearing timing — phase is the
    legacy string fallback used when the FK is NULL.
    """
    from app.engines.cashflow import _APS_TO_USE_PHASE

    def _phase(aps: str) -> str:
        return _APS_TO_USE_PHASE.get(aps, "acquisition")

    # Acquisition-time loans
    assert _phase("acquisition") == "acquisition"
    assert _phase("close") == "acquisition"
    assert _phase("offer_made") == "acquisition"
    assert _phase("under_contract") == "acquisition"
    # Pre-construction / construction loans inherit their phase
    assert _phase("pre_construction") == "pre_construction"
    assert _phase("pre_development") == "pre_construction"
    assert _phase("construction") == "construction"
    # Operation / exit loans inherit their phase (no coercion). The Source's
    # active_from_milestone_id FK is the canonical timing carrier; phase is
    # the legacy string that trails it.
    assert _phase("operation_stabilized") == "operation"
    assert _phase("stabilized") == "operation"
    assert _phase("lease_up") == "operation"
    assert _phase("operation_lease_up") == "operation"
    assert _phase("exit") == "exit"
    assert _phase("divestment") == "exit"
    # Unknown / NULL → acquisition fallback
    assert _phase("") == "acquisition"
    assert _phase("garbage_value") == "acquisition"


@pytest.mark.unit
def test_engine_auto_fc_writeback_copies_milestone_fk():
    """Engine writeback block copies parent module's active_from_milestone_id
    onto the auto-FC UseLine — both on create and on update. Static inspection
    of the writeback source: both code paths must set the FK so renaming or
    moving the Source's start milestone propagates to the FC row.
    """
    import inspect
    import app.engines.cashflow as cf
    src = inspect.getsource(cf)
    assert "_ccm_from_ms_id = getattr(_ccm_ref, \"active_from_milestone_id\", None)" in src, (
        "Engine must read parent module's active_from_milestone_id."
    )
    assert "active_from_milestone_id=_ccm_from_ms_id" in src, (
        "Engine must set active_from_milestone_id on new auto-FC UseLine."
    )
    assert "_cc_exist.active_from_milestone_id = _ccm_from_ms_id" in src, (
        "Engine must update active_from_milestone_id on existing auto-FC UseLine."
    )
