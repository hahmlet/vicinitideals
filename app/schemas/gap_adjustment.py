"""Request/response schemas for the Gap Adjustment slider endpoint.

The slider drawer in the UI sends a SliderRequest after the user releases
each slider; the endpoint upserts the three phantom rows (one per slider)
and re-runs compute_cash_flows, returning a SliderResponse with the new
DSCR / LTV / equity / Sources-Uses gap so the pill and panel can swap.

Only the deltas explicitly included in the request are touched. Sliders
that the user hasn't moved this round are left untouched (their phantom
rows keep their prior amounts). Pass an explicit ``0`` to zero out a
slider; pass ``None`` (omit) to leave it alone.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SliderRequest(BaseModel):
    """Three deltas — revenue (monthly), opex (annual), purchase price.

    All three are optional and treated as absolute target values for the
    corresponding phantom row, not increments. ``None`` (omitted field)
    means "leave that phantom row untouched"; ``0`` means "set the phantom
    row to zero" (which the UI may show as gray / un-highlighted).

    Negative values are explicitly supported: a negative ``opex_delta_annual``
    means "imagine opex were $X lower"; a negative ``pp_delta`` means
    "imagine purchase price were $X lower" and reduces total Uses.
    """

    revenue_delta_monthly: Decimal | None = None
    opex_delta_annual: Decimal | None = None
    pp_delta: Decimal | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "revenue_delta_monthly": "1000",
                "opex_delta_annual": "-12000",
                "pp_delta": "-50000",
            }
        }
    )


class SliderResponse(BaseModel):
    """Post-compute metrics after applying the slider deltas.

    All metrics reflect the scenario including the phantom rows; the UI
    consumes this to update the calc-status pill and the Sources/Uses panel.
    """

    revenue_delta_monthly: Decimal
    opex_delta_annual: Decimal
    pp_delta: Decimal
    has_any_adjustment: bool
    """True iff any of the three deltas is non-zero. Drives the pill's
    yellow override (any nonzero adjustment → all pill items yellow even
    when thresholds pass)."""

    dscr: Decimal | None = None
    total_project_cost: Decimal | None = None
    equity_required: Decimal | None = None
