"""Apply a scenario template's structural data to a newly-created project."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import IncomeStream, OperatingExpenseLine, OperationalInputs


async def apply_template_to_project(
    session: AsyncSession,
    template_json: dict[str, Any],
    project_id: UUID,
) -> None:
    """Seed income streams, expense lines, and debt stack from a template into a project."""
    for s in template_json.get("income_streams") or []:
        stream_type = s.get("stream_type") or "residential_rent"
        label = s.get("label") or "Income"
        try:
            occ = Decimal(str(s.get("stabilized_occupancy_pct") or 95))
        except Exception:
            occ = Decimal("95")
        try:
            esc = Decimal(str(s.get("escalation_rate_pct_annual") or 0))
        except Exception:
            esc = Decimal("0")
        session.add(IncomeStream(
            project_id=project_id,
            stream_type=stream_type,
            label=label,
            stabilized_occupancy_pct=occ,
            bad_debt_pct=Decimal(str(s.get("bad_debt_pct") or 0)),
            concessions_pct=Decimal(str(s.get("concessions_pct") or 0)),
            escalation_rate_pct_annual=esc,
            active_in_phases=s.get("active_in_phases") or [],
            notes=s.get("notes"),
        ))

    for e in template_json.get("expense_lines") or []:
        label = e.get("label") or "Expense"
        try:
            esc = Decimal(str(e.get("escalation_rate_pct_annual") or 3))
        except Exception:
            esc = Decimal("3")
        session.add(OperatingExpenseLine(
            project_id=project_id,
            label=label,
            annual_amount=Decimal("0"),
            per_type="flat",
            scale_with_lease_up=bool(e.get("scale_with_lease_up")),
            escalation_rate_pct_annual=esc,
            active_in_phases=e.get("active_in_phases") or [],
            notes=e.get("notes"),
        ))

    # Seed debt_types and debt_terms (Source Vehicle per loan type) from template.
    tmpl_oi = template_json.get("operational_inputs") or {}
    tmpl_debt_types = tmpl_oi.get("debt_types") or []
    tmpl_debt_terms = tmpl_oi.get("debt_terms") or {}
    if tmpl_debt_types or tmpl_debt_terms:
        oi = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )).scalar_one_or_none()
        if oi is not None:
            if tmpl_debt_types:
                oi.debt_types = tmpl_debt_types
            if tmpl_debt_terms:
                merged = dict(oi.debt_terms or {})
                for ft, terms in tmpl_debt_terms.items():
                    if ft not in merged:
                        merged[ft] = terms
                    elif terms.get("vehicle_id") and not merged[ft].get("vehicle_id"):
                        merged[ft] = {**merged[ft], "vehicle_id": terms["vehicle_id"]}
                oi.debt_terms = merged
            session.add(oi)
