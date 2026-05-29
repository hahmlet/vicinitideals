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

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SliderRequest(BaseModel):
    """Gap adjuster deltas — revenue/opex (annual) or NOI (annual), plus purchase price.

    All fields are optional absolute target values for the corresponding phantom
    row, not increments. ``None`` (omitted) means "leave that phantom row
    untouched"; ``0`` means "zero it out".

    revenue_opex mode: use ``revenue_delta_annual`` and ``opex_delta_annual``.
    noi mode: use ``noi_delta_annual``; revenue/opex fields are ignored.
    ``pp_delta`` applies in both modes.

    Negative values are explicitly supported: a negative ``opex_delta_annual``
    means "imagine opex were $X lower"; a negative ``pp_delta`` means
    "imagine purchase price were $X lower" and reduces total Uses.
    """

    revenue_delta_annual: Decimal | None = None
    opex_delta_annual: Decimal | None = None
    noi_delta_annual: Decimal | None = None
    pp_delta: Decimal | None = None
    # Multi-project deals: phantom rows must land on the project the user is
    # currently viewing. Omit (default) → endpoint uses the scenario's
    # default (first) project — the single-project case.
    project_id: uuid.UUID | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "revenue_delta_annual": "12000",
                "opex_delta_annual": "-12000",
                "pp_delta": "-50000",
                "project_id": "44444444-4444-4444-4444-444444444444",
            }
        }
    )


class SliderResponse(BaseModel):
    """Post-compute metrics after applying the slider deltas.

    All metrics reflect the scenario including the phantom rows; the UI
    consumes this to update the calc-status pill and the Sources/Uses panel.
    """

    revenue_delta_annual: Decimal
    opex_delta_annual: Decimal
    noi_delta_annual: Decimal
    pp_delta: Decimal
    has_any_adjustment: bool
    """True iff any delta is non-zero. Drives the pill's yellow override."""

    dscr: Decimal | None = None
    total_project_cost: Decimal | None = None
    equity_required: Decimal | None = None
