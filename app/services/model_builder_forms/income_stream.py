"""Form-save logic for IncomeStream rows (Revenue panel)."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import IncomeStream
from app.utils.form_helpers import _fd, _fi, _fp


async def save_income_stream(
    session: AsyncSession,
    project_id: UUID | None,
    item_id: str,
    form,
) -> None:
    """Persist an IncomeStream create or update from form data."""
    _amount_type = str(form.get("amount_type", "")).strip()
    _per_unit_val = _fd(form.get("amount_per_unit_monthly"))
    _fixed_val = _fd(form.get("amount_fixed_monthly"))
    # Clear the unused field so engine logic is unambiguous.
    if _amount_type == "flat":
        _per_unit_val = None
    elif _amount_type == "per_unit":
        _fixed_val = None
    data = {
        "label": form.get("label", ""),
        "stream_type": form.get("stream_type", "residential_rent"),
        "unit_count": _fi(form.get("unit_count")) or None,
        "amount_per_unit_monthly": _per_unit_val,
        "amount_fixed_monthly": _fixed_val,
        "stabilized_occupancy_pct": _fd(form.get("stabilized_occupancy_pct")) or Decimal("95"),
        "bad_debt_pct": _fd(form.get("bad_debt_pct")) or Decimal("0"),
        "concessions_pct": _fd(form.get("concessions_pct")) or Decimal("0"),
        "catchup_target_rent": _fd(form.get("catchup_target_rent")),
        "renovation_absorption_rate": _fd(form.get("renovation_absorption_rate")),
        "escalation_rate_pct_annual": _fd(form.get("escalation_rate_pct_annual")) or Decimal("0"),
        "active_in_phases": form.getlist("active_in_phases") or _fp(form.get("active_in_phases"), ["stabilized"]),
        "notes": form.get("notes") or None,
    }
    if item_id:
        row = await session.get(IncomeStream, UUID(item_id))
        if row:
            for k, v in data.items():
                setattr(row, k, v)
    elif project_id:
        session.add(IncomeStream(project_id=project_id, **data))
