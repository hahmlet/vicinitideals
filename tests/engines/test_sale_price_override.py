"""Manual sale-price override beats cap-rate valuation in the exit reversion.

Exercises ``app/engines/cashflow.py::_phase_capital_events`` exit branch:

- override set (> 0) wins over stabilized NOI / exit_cap, even with positive NOI
- override rescues exits whose stabilized NOI is negative (the cap-rate path
  would otherwise emit a negative / meaningless sale price)
- no override + positive NOI → unchanged cap-rate valuation
- no override + negative NOI → negative sale price (the bug the override fixes)
- override of 0 falls back to cap-rate (treated as "not set")
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.engines.cashflow import _phase_capital_events
from app.engines.cashflow_compile import PhaseSpec
from app.models.cashflow import PeriodType
from app.models.deal import OperationalInputs

pytestmark = pytest.mark.unit


def _exit_inputs(**overrides: object) -> OperationalInputs:
    base: dict[str, object] = {
        "exit_cap_rate_pct": Decimal("5"),
        "selling_costs_pct": Decimal("0"),
        "sale_price_override": None,
        "noi_escalation_rate_pct": None,
    }
    base.update(overrides)
    return OperationalInputs(**base)


def _sale_proceeds(inputs: OperationalInputs, noi_monthly: Decimal) -> Decimal:
    items = _phase_capital_events(
        phase=PhaseSpec(period_type=PeriodType.exit, months=1),
        inputs=inputs,
        month_index=0,
        deal_model_id=uuid.uuid4(),
        period=0,  # == first_stab_period → no NOI escalation applied
        stabilized_noi_monthly=noi_monthly,
        has_use_lines=True,
        first_stab_period=0,
    )
    sale = [i for i in items if i.label == "Sale Proceeds"]
    assert len(sale) == 1
    return Decimal(str(sale[0].net_amount))


def test_cap_rate_valuation_when_no_override() -> None:
    # 10k/mo NOI → 120k/yr ÷ 5% = 2.4M
    assert _sale_proceeds(_exit_inputs(), Decimal("10000")) == Decimal("2400000")


def test_override_wins_over_cap_rate_with_positive_noi() -> None:
    inputs = _exit_inputs(sale_price_override=Decimal("5000000"))
    # Cap-rate path would give 2.4M; override must win.
    assert _sale_proceeds(inputs, Decimal("10000")) == Decimal("5000000")


def test_negative_noi_without_override_produces_negative_sale_price() -> None:
    # Documents the failure the override exists to fix.
    assert _sale_proceeds(_exit_inputs(), Decimal("-5000")) < Decimal("0")


def test_override_rescues_negative_noi_exit() -> None:
    inputs = _exit_inputs(sale_price_override=Decimal("3000000"))
    assert _sale_proceeds(inputs, Decimal("-5000")) == Decimal("3000000")


def test_zero_override_falls_back_to_cap_rate() -> None:
    inputs = _exit_inputs(sale_price_override=Decimal("0"))
    assert _sale_proceeds(inputs, Decimal("10000")) == Decimal("2400000")
