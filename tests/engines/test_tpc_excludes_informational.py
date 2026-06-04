"""Regression test for Slice 4 (Export v3): the engine's
_calculate_total_project_cost must exclude capital_event line items
whose direction is "informational".

Background. Float Earnings (Found Money) recycle back into the
GP/LP waterfall at the waterfall milestone period. The engine
records that recycling as a capital_event line item with
``direction="informational"`` so the cashflow series ties out, but
the recycled cash is NOT a true project cost — it is internal
movement of already-funded capital. Counting it in TPC double-counts
the Float Earnings amount and inflates the engine's TPC vs. the
Excel TPC (which sums only UseLines minus balance-only).

Live-deal example (cf0e77c3, 2026-06-03 prod validation):
  engine TPC: $13,614,673
  Excel TPC: $13,311,629
  diff:      $303,043.93  ← Float Earnings amount

Filter contract:
- ``direction == "outflow"`` → counted (true cost)
- ``direction == "inflow"``  → NOT counted (source row)
- ``direction == "informational"`` → NOT counted (Float Earnings
  waterfall recycling; new in Float Earnings Phase B, 2026-06-02)
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.cashflow import _calculate_total_project_cost
from app.models.cashflow import CashFlowLineItem, LineItemCategory


pytestmark = pytest.mark.unit


def _ce(label: str, amount: Decimal, direction: str) -> CashFlowLineItem:
    """One capital_event line item with the given direction."""
    return CashFlowLineItem(
        scenario_id=uuid.uuid4(),
        project_id=None,
        period=1,
        income_stream_id=None,
        category=LineItemCategory.capital_event,
        label=label,
        base_amount=amount,
        adjustments={"direction": direction},
        net_amount=amount,
    )


def test_outflow_counted_inflow_excluded():
    items = [
        _ce("Hard Costs", Decimal("100"), "outflow"),
        _ce("Loan Proceeds", Decimal("80"), "inflow"),
    ]
    assert _calculate_total_project_cost(items) == Decimal("100")


def test_informational_excluded():
    """Float Earnings → Waterfall lines must not inflate TPC."""
    items = [
        _ce("Land", Decimal("4000000"), "outflow"),
        _ce("Found Money → Waterfall (abc12345…)", Decimal("303043.93"), "informational"),
    ]
    # The informational line is dropped — TPC is the outflow only.
    assert _calculate_total_project_cost(items) == Decimal("4000000")


def test_missing_direction_treated_as_non_outflow():
    """Defensive: a capital_event with no direction marker should NOT
    contribute to TPC. Old code coerced missing → not-inflow → counted;
    the tightened filter treats it as non-outflow → excluded."""
    items = [
        CashFlowLineItem(
            scenario_id=uuid.uuid4(),
            project_id=None,
            period=1,
            income_stream_id=None,
            category=LineItemCategory.capital_event,
            label="Mystery row",
            base_amount=Decimal("500"),
            adjustments=None,
            net_amount=Decimal("500"),
        ),
    ]
    assert _calculate_total_project_cost(items) == Decimal("0")


def test_non_capital_event_categories_ignored():
    """Only capital_event lines participate in TPC."""
    items = [
        _ce("Hard Costs", Decimal("100"), "outflow"),
        CashFlowLineItem(
            scenario_id=uuid.uuid4(),
            project_id=None,
            period=1,
            income_stream_id=None,
            category=LineItemCategory.expense,
            label="OpEx",
            base_amount=Decimal("50"),
            adjustments={"direction": "outflow"},
            net_amount=Decimal("50"),
        ),
    ]
    assert _calculate_total_project_cost(items) == Decimal("100")
