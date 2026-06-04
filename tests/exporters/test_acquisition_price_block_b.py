"""Block B "Acquisition Price" on the Assumptions sheet must return the
true purchase price — not the sum of every phase=acquisition Use line.

Background. The engine auto-tags many cost rows (Dev Fee, Interest
Reserve, ODR, Operating Reserve, Finance Costs) with
``phase="acquisition"`` because they fund at close. Block B's old
helper summed every UseLine where phase=="acquisition" and called the
total "Acquisition Price". On a deal with $3.4M of land + $3.5M of
acquisition-phase soft costs, Block B would render $6.9M as
"Acquisition Price" — wrong by ~$3.5M.

Fix: prefer ``Project.acquisition_price`` when set; else sum only
UseLines with ``cost_category == "acquisition"`` (the true land rows).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.exporters.investor_export import _per_project_value_raw


class _UL:
    """Minimal stub matching the UseLine attrs the helper reads."""

    def __init__(self, amount, phase, cost_category):
        self.amount = Decimal(str(amount))
        self.phase = phase
        self.cost_category = cost_category


class _Project:
    def __init__(self, acquisition_price=None):
        self.acquisition_price = acquisition_price
        self.name = "P"
        self.deal_type = "new_construction"


@pytest.mark.unit
def test_explicit_acquisition_price_wins():
    proj = _Project(acquisition_price=Decimal("2500000"))
    use_lines = [
        _UL(3400000, "acquisition", "acquisition"),
        _UL(1231629, "acquisition", "soft"),
    ]
    out = _per_project_value_raw("acquisition_price", proj, None, use_lines, [])
    assert out == Decimal("2500000")


@pytest.mark.unit
def test_fallback_filters_to_acquisition_category_only():
    """No project.acquisition_price → sum only cost_category=='acquisition'.
    Soft costs that happen to share phase=acquisition are excluded."""
    proj = _Project(acquisition_price=None)
    use_lines = [
        _UL(3400000, "acquisition", "acquisition"),       # land — included
        _UL(0,       "acquisition", "acquisition"),       # gap adj — included
        _UL(1231629, "acquisition", "soft"),               # Dev Fee — excluded
        _UL(1269898, "acquisition", "soft"),               # IR — excluded
        _UL(11727,   "acquisition", "soft"),               # ODR — excluded
        _UL(471949,  "acquisition", "soft"),               # Op Reserve — excluded
        _UL(350000,  "acquisition", "soft"),               # Finance Costs — excluded
        _UL(170000,  "acquisition", "soft"),               # Acq Fee — excluded
        _UL(8160000, "construction", "hard"),              # Hard Costs — excluded (phase)
    ]
    out = _per_project_value_raw("acquisition_price", proj, None, use_lines, [])
    assert out == Decimal("3400000")


@pytest.mark.unit
def test_fallback_returns_none_when_no_acquisition_lines():
    proj = _Project(acquisition_price=None)
    use_lines = [_UL(8160000, "construction", "hard")]
    out = _per_project_value_raw("acquisition_price", proj, None, use_lines, [])
    assert out is None
