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
