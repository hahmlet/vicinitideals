"""Template render test: OpEx panel surfaces CapEx Reserve as locked row.

CapEx Reserve is set on OperationalInputs (Deal Settings) but is deducted
from NOI alongside line-item OpEx. The OpEx tab renders it as a synthetic
locked row so users see the full NOI deduction in one place.

Tests render the model_builder_panel.html partial directly via Jinja2 to
avoid the SQLite/JSONB ORM bootstrap issue tracked separately.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.routers.ui import templates


def _make_env():
    return templates.env


def _render_opex_panel(
    *,
    capex_per_unit: float,
    total_units: int,
    expense_lines: list | None = None,
    opex_annual: float | None = None,
    expense_growth: float = 3.0,
) -> str:
    env = _make_env()
    tpl = env.get_template("partials/model_builder_panel.html")
    inputs = SimpleNamespace(
        capex_reserve_per_unit_annual=Decimal(str(capex_per_unit)),
        expense_growth_rate_pct_annual=Decimal(str(expense_growth)),
    )
    model = SimpleNamespace(id="00000000-0000-0000-0000-000000000001")
    return tpl.render(
        active_module="opex",
        model=model,
        inputs=inputs,
        expense_lines=expense_lines or [],
        opex_annual=opex_annual or 0,
        total_units=total_units,
        _GAP_OPEX_LBL="OpEx Adjustment",
        capital_modules=[],
        capital_total=0,
        capital_junction_amts={},
    )


def test_opex_panel_renders_capex_reserve_row() -> None:
    html = _render_opex_panel(capex_per_unit=600, total_units=8, opex_annual=50000)

    assert "CapEx Reserve" in html
    assert "Edit in Deal Settings" in html
    assert "model-settings-drawer" in html  # click target opens drawer
    # $600/unit/yr × 8 units = $4,800/yr
    assert "$4,800" in html
    assert "Total NOI Deduction" in html


def test_opex_panel_hides_capex_reserve_when_zero_units() -> None:
    html = _render_opex_panel(capex_per_unit=600, total_units=0, opex_annual=50000)

    assert "Edit in Deal Settings" not in html
    assert "Total NOI Deduction" not in html


def test_opex_panel_hides_capex_reserve_when_per_unit_zero() -> None:
    html = _render_opex_panel(capex_per_unit=0, total_units=8, opex_annual=50000)

    assert "Edit in Deal Settings" not in html
    assert "Total NOI Deduction" not in html


@pytest.mark.parametrize(
    "per_unit,units,expected",
    [
        (250, 8, "$2,000"),
        (300, 100, "$30,000"),
        (425, 24, "$10,200"),
    ],
)
def test_opex_panel_capex_reserve_math(per_unit: int, units: int, expected: str) -> None:
    html = _render_opex_panel(capex_per_unit=per_unit, total_units=units, opex_annual=0)
    assert expected in html
