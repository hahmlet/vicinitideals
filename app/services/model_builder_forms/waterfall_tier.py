"""Form-save logic for WaterfallTier rows (Owner's Profit panel)."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import WaterfallTier
from app.utils.form_helpers import _fd, _fi


async def save_waterfall_tier(
    session: AsyncSession,
    model_id: UUID,
    item_id: str,
    form,
) -> None:
    """Persist a WaterfallTier create or update from form data."""
    data = {
        "priority": _fi(form.get("priority"), 1),
        "tier_type": form.get("tier_type", "residual"),
        "description": form.get("description") or None,
        "lp_split_pct": _fd(form.get("lp_split_pct")) or Decimal("0"),
        "gp_split_pct": _fd(form.get("gp_split_pct")) or Decimal("0"),
        "irr_hurdle_pct": _fd(form.get("irr_hurdle_pct")),
        "max_pct_of_distributable": _fd(form.get("max_pct_of_distributable")),
        "interest_rate_pct": _fd(form.get("interest_rate_pct")),
    }
    if item_id:
        row = await session.get(WaterfallTier, UUID(item_id))
        if row:
            for k, v in data.items():
                setattr(row, k, v)
    else:
        session.add(WaterfallTier(scenario_id=model_id, **data))
