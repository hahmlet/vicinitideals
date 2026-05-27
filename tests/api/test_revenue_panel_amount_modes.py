"""Template render tests: Revenue panel amount-mode math in table rows.

These tests protect against a regression where fixed monthly revenue rows were
multiplied by unit_count in the panel preview.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.api.routers.ui import templates


def _make_stream(*, unit_count: int | None, per_unit: Decimal | None, fixed: Decimal | None):
    return SimpleNamespace(
        id="r-1",
        label="Test Revenue",
        stream_type="other",
        unit_count=unit_count,
        amount_per_unit_monthly=per_unit,
        amount_fixed_monthly=fixed,
        stabilized_occupancy_pct=Decimal("100"),
        escalation_rate_pct_annual=Decimal("3"),
    )


def _render_revenue_panel(stream) -> str:
    tpl = templates.env.get_template("partials/model_builder_panel.html")
    return tpl.render(
        active_module="revenue",
        model=SimpleNamespace(id="00000000-0000-0000-0000-000000000001"),
        income_streams=[stream],
        expense_lines=[],
        use_lines=[],
        capital_modules=[],
        unit_mix_rows=[],
        inputs=SimpleNamespace(purchase_price=Decimal("0")),
        total_units=0,
        uses_total=0,
        capital_total=0,
        capital_junction_amts={},
        revenue_annual=0,
        _GAP_REV_LBL="Revenue Adjustment",
        _GAP_OPEX_LBL="OpEx Adjustment",
        _GAP_PP_LBL="Purchase Price Adjustment",
    )


def test_revenue_panel_flat_amount_not_scaled_by_units() -> None:
    html = _render_revenue_panel(
        _make_stream(
            unit_count=10,
            per_unit=None,
            fixed=Decimal("1000"),
        )
    )

    assert "$12,000" in html
    assert "$120,000" not in html


def test_revenue_panel_per_unit_amount_scales_by_units() -> None:
    html = _render_revenue_panel(
        _make_stream(
            unit_count=10,
            per_unit=Decimal("1000"),
            fixed=None,
        )
    )

    assert "$120,000" in html
