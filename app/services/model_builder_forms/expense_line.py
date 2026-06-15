"""Form-save logic for OperatingExpenseLine rows (OpEx panel)."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import OperatingExpenseLine
from app.utils.form_helpers import _fd, _fp


async def save_expense_line(
    session: AsyncSession,
    project_id: UUID | None,
    item_id: str,
    form,
) -> None:
    """Persist an OperatingExpenseLine create or update from form data."""
    _aip_list = form.getlist("active_in_phases")
    active_phases = _aip_list if _aip_list else _fp(form.get("active_in_phases"), ["stabilized"])
    per_type_val = form.get("per_type") or None
    per_value_val = _fd(form.get("per_value"))
    # For flat type, annual_amount mirrors per_value for backward-compat display
    # For per_unit/sqft types, annual_amount stays 0 until compute engine scales it
    if per_value_val and per_type_val in (None, "flat"):
        annual_amt = per_value_val
    else:
        annual_amt = _fd(form.get("annual_amount")) or Decimal("0")
    data = {
        "label": form.get("label", ""),
        "annual_amount": annual_amt,
        "per_value": per_value_val,
        "per_type": per_type_val,
        "scale_with_lease_up": form.get("scale_with_lease_up") == "on",
        "lease_up_floor_pct": _fd(form.get("lease_up_floor_pct")),
        "escalation_rate_pct_annual": _fd(form.get("escalation_rate_pct_annual")) or Decimal("3"),
        "active_in_phases": active_phases,
        "notes": form.get("notes") or None,
    }
    if item_id:
        row = await session.get(OperatingExpenseLine, UUID(item_id))
        if row:
            for k, v in data.items():
                setattr(row, k, v)
    elif project_id:
        session.add(OperatingExpenseLine(project_id=project_id, **data))
