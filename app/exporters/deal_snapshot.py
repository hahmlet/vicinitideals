"""Full-fidelity deal snapshot payload for Scenario Library capture.

The payload is intentionally import-oriented:
- `portable_deal_v1` keeps current import compatibility.
- `full_snapshot` preserves near-raw persisted rows for eventual 100% parity import.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.deal_export import DEAL_EXPORT_VERSION, export_deal_json
from app.models.capital import CapitalModule, CapitalModuleProject, DrawSource, WaterfallTier
from app.models.deal import Deal, DealModel, IncomeStream, OperatingExpenseLine, OperationalInputs, UseLine
from app.models.milestone import Milestone
from app.models.project import Project, ProjectAnchor


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    return value


def _row_to_dict(row: Any, *, include_id: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col in row.__table__.columns:
        key = col.key
        if not include_id and key == "id":
            continue
        data[key] = _json_value(getattr(row, key, None))
    return data


async def export_full_deal_snapshot(session: AsyncSession, deal_id: UUID) -> dict[str, Any]:
    """Export a capture payload intended for Scenario Library snapshot storage."""
    deal = await session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"Deal {deal_id} not found")

    portable_payload = await export_deal_json(session=session, deal_id=deal_id)

    scenarios = list((await session.execute(
        select(DealModel).where(DealModel.deal_id == deal_id).order_by(DealModel.created_at.asc())
    )).scalars())
    scenario_ids = [s.id for s in scenarios]

    projects = []
    if scenario_ids:
        projects = list((await session.execute(
            select(Project).where(Project.scenario_id.in_(scenario_ids)).order_by(Project.created_at.asc())
        )).scalars())
    project_ids = [p.id for p in projects]

    opportunities: list[Any] = []
    seen_opp_ids: set[UUID] = set()
    for p in projects:
        if p.opportunity_id and p.opportunity_id not in seen_opp_ids:
            seen_opp_ids.add(p.opportunity_id)
    if seen_opp_ids:
        from app.models.opportunity import Opportunity
        opportunities = list((await session.execute(
            select(Opportunity).where(Opportunity.id.in_(seen_opp_ids)).order_by(Opportunity.last_seen_at.asc())
        )).scalars())

    operational_inputs = []
    use_lines = []
    expense_lines = []
    income_streams = []
    milestones = []
    anchors = []
    if project_ids:
        operational_inputs = list((await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id.in_(project_ids))
        )).scalars())
        use_lines = list((await session.execute(
            select(UseLine).where(UseLine.project_id.in_(project_ids))
        )).scalars())
        expense_lines = list((await session.execute(
            select(OperatingExpenseLine).where(OperatingExpenseLine.project_id.in_(project_ids))
        )).scalars())
        income_streams = list((await session.execute(
            select(IncomeStream).where(IncomeStream.project_id.in_(project_ids))
        )).scalars())
        milestones = list((await session.execute(
            select(Milestone).where(Milestone.project_id.in_(project_ids))
        )).scalars())
        anchors = list((await session.execute(
            select(ProjectAnchor).where(ProjectAnchor.project_id.in_(project_ids))
        )).scalars())

    if seen_opp_ids:
        opp_milestones = list((await session.execute(
            select(Milestone).where(Milestone.opportunity_id.in_(seen_opp_ids))
        )).scalars())
        milestones.extend(opp_milestones)

    capital_modules = []
    cap_project_terms = []
    draw_sources = []
    waterfall_tiers = []
    if scenario_ids:
        capital_modules = list((await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id.in_(scenario_ids))
        )).scalars())
        module_ids = [m.id for m in capital_modules]
        if module_ids:
            cap_project_terms = list((await session.execute(
                select(CapitalModuleProject).where(CapitalModuleProject.capital_module_id.in_(module_ids))
            )).scalars())
        draw_sources = list((await session.execute(
            select(DrawSource).where(DrawSource.scenario_id.in_(scenario_ids))
        )).scalars())
        waterfall_tiers = list((await session.execute(
            select(WaterfallTier).where(WaterfallTier.scenario_id.in_(scenario_ids))
        )).scalars())

    return {
        "snapshot_version": "ui-full-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "deal_id": str(deal.id),
            "deal_name": deal.name,
            "org_id": str(deal.org_id),
        },
        "portable": {
            "format": DEAL_EXPORT_VERSION,
            "payload": portable_payload,
        },
        "full_snapshot": {
            "deal": _row_to_dict(deal),
            "opportunities": [_row_to_dict(o) for o in opportunities],
            "scenarios": [_row_to_dict(s) for s in scenarios],
            "projects": [_row_to_dict(p) for p in projects],
            "operational_inputs": [_row_to_dict(r) for r in operational_inputs],
            "use_lines": [_row_to_dict(r) for r in use_lines],
            "expense_lines": [_row_to_dict(r) for r in expense_lines],
            "income_streams": [_row_to_dict(r) for r in income_streams],
            "milestones": [_row_to_dict(r) for r in milestones],
            "project_anchors": [_row_to_dict(r) for r in anchors],
            "capital_modules": [_row_to_dict(r) for r in capital_modules],
            "capital_module_projects": [_row_to_dict(r) for r in cap_project_terms],
            "draw_sources": [_row_to_dict(r) for r in draw_sources],
            "waterfall_tiers": [_row_to_dict(r) for r in waterfall_tiers],
        },
    }
