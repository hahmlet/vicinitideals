"""Canonical JSON export helpers for portable deal-model payloads."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deal import Scenario
from app.models.project import Opportunity, Project, ProjectCategory, ProjectSource, ProjectStatus
from app.schemas.capital import (
    CapitalModuleRead,
    DrawSourceRead,
    WaterfallResultRead,
    WaterfallTierRead,
)
from app.schemas.deal import (
    CashFlowRead,
    ScenarioRead,
    IncomeStreamRead,
    UnitMixRead,
    OperatingExpenseLineRead,
    OperationalInputsRead,
    OperationalOutputsRead,
    UseLineRead,
)

# v2 (April 2026): Phase B fields added to OperationalInputsBase
# (debt_types, debt_terms, debt_milestone_config, debt_sizing_mode,
# dscr_minimum, operation_reserve_months, construction_floor_pct,
# noi_stabilized_input, noi_escalation_rate_pct, deal_setup_complete,
# debt_structure). ScenarioBase gained income_mode. CapitalCarrySchema
# and CapitalSourceSchema became permissive (extra="allow") and gained
# the Phase 1 fields (io_rate_pct, amort_term_years, phases, auto_size,
# is_bridge, etc.) so carry and source JSONB columns round-trip without
# silently dropping keys.
#
# v3 (July 2026): the export gained `use_lines`, `milestones` (with stable
# ids + trigger_milestone_id chains so import can rewire them), and
# `draw_sources` blocks; import additionally accepts `unit_mix` (which v2
# already exported).  The Base schemas were widened to mirror the ORM:
# CapitalModuleBase (+eligible_use_tags, source_vehicle_id, milestone FK
# anchors), WaterfallTierBase (+project_id), ScenarioBase (+min_reserve_*,
# risk_free/discount rates, health_thresholds, source_vehicle_id),
# OperationalInputsBase (+entitlement_cost, going_in_cap_rate_pct,
# noi_auto_seeded, affordable_housing_project), UseLineBase
# (+eligible_module_ids, is_auto_*, dev_fee_* fields).  v1/v2 payloads
# still import unchanged.
EXPORT_SCHEMA_VERSION = "deal-json-v3"


def _json_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _dump_optional(schema_cls: type, value: object | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return schema_cls.model_validate(value).model_dump(mode="json")


def _split_reso_address(address: str | None) -> tuple[str | None, str | None, str | None]:
    if not address:
        return None, None, None

    cleaned = " ".join(str(address).replace("\n", " ").split())
    match = re.search(r"(?P<state>[A-Z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)$", cleaned)
    if not match:
        return None, None, None

    state = match.group("state")
    postal = match.group("postal")
    prefix = cleaned[: match.start()].strip(" ,")

    if "," in prefix:
        parts = [part.strip() for part in prefix.split(",") if part.strip()]
        city = parts[-1] if parts else None
    else:
        parts = prefix.split()
        city = parts[-1] if parts else None

    return city, state, postal


def _build_project_payload(project: Opportunity | None) -> dict[str, Any]:
    address = None if project is None else (project.address_normalized or project.address_raw)
    city, state, postal = _split_reso_address(address)

    status = None
    project_category = None
    source = None
    if project is not None:
        status = _json_scalar(project.status or ProjectStatus.hypothetical)
        project_category = _json_scalar(project.project_category or ProjectCategory.proposed)
        source = _json_scalar(project.source or ProjectSource.manual)

    return {
        "Name": None if project is None else project.name,
        "UnparsedAddress": address,
        "City": city,
        "StateOrProvince": state,
        "PostalCode": postal,
        "ParcelNumber": None if project is None else project.apn,
        "LotSizeSquareFeet": None if project is None else _json_scalar(project.lot_sqft),
        "YearBuilt": None if project is None else project.year_built,
        "BuildingAreaTotal": None if project is None else _json_scalar(project.gba_sqft),
        "PropertyType": None if project is None else project.property_type,
        "Status": status,
        "ProjectCategory": project_category,
        "Source": source,
    }


async def export_deal_model_json(session: AsyncSession, model_id: UUID) -> dict[str, Any]:
    """Return a canonical JSON payload for a deal model and its nested records."""
    result = await session.execute(
        select(Scenario)
        .options(
            selectinload(Scenario.projects).options(
                selectinload(Project.operational_inputs),
                selectinload(Project.income_streams),
                selectinload(Project.expense_lines),
                selectinload(Project.use_lines),
                selectinload(Project.milestones),
                selectinload(Project.opportunity),
            ),
            selectinload(Scenario.operational_outputs),
            selectinload(Scenario.cash_flows),
            selectinload(Scenario.capital_modules),
            selectinload(Scenario.waterfall_tiers),
            selectinload(Scenario.waterfall_results),
            selectinload(Scenario.draw_sources),
        )
        .where(Scenario.id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("Deal model not found")

    # Load Opportunity (purchase target) for project metadata via first Project
    opportunity = None
    opportunity_id = next(
        (p.opportunity_id for p in model.projects if p.opportunity_id is not None), None
    ) if model.projects else None
    if opportunity_id:
        opp_result = await session.execute(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
        )
        opportunity = opp_result.scalar_one_or_none()

    # Get default dev Project for line items
    default_project = next(
        (p for p in sorted(model.projects, key=lambda p: p.created_at)), None
    ) if model.projects else None

    operational_inputs = _dump_optional(OperationalInputsRead, default_project.operational_inputs if default_project else None)
    outputs = _dump_optional(OperationalOutputsRead, model.operational_outputs)
    income_streams = [
        IncomeStreamRead.model_validate(stream).model_dump(mode="json")
        for stream in sorted(default_project.income_streams if default_project else [], key=lambda item: (item.label or "", str(item.id)))
    ]
    expense_lines = [
        OperatingExpenseLineRead.model_validate(line).model_dump(mode="json")
        for line in sorted(default_project.expense_lines if default_project else [], key=lambda item: (item.label or "", str(item.id)))
    ]
    # unit_mix is JSONB on Project (migration 0067) — pass dicts through
    # rather than re-validating with UnitMixRead, which expects id +
    # project_id fields the JSONB form never carries.
    unit_mix = sorted(
        list(default_project.unit_mix if default_project and default_project.unit_mix else []),
        key=lambda item: (item.get("label") or "", str(item.get("id") or "")),
    )
    # v3: use_lines carry stable ids so import can remap eligible_module_ids
    # and milestone FKs onto the newly created rows.
    use_lines = [
        UseLineRead.model_validate(line).model_dump(mode="json")
        for line in sorted(
            default_project.use_lines if default_project else [],
            key=lambda item: (item.label or "", str(item.id)),
        )
    ]
    # v3: milestones export stable ids + trigger_milestone_id chains; import
    # re-creates them two-pass and rewires the chains to the new ids.
    milestones = [
        {
            "id": str(ms.id),
            "milestone_type": _json_scalar(ms.milestone_type),
            "duration_days": ms.duration_days,
            "target_date": ms.target_date.isoformat() if ms.target_date else None,
            "sequence_order": ms.sequence_order,
            "label": ms.label,
            "trigger_milestone_id": str(ms.trigger_milestone_id) if ms.trigger_milestone_id else None,
            "trigger_offset_days": ms.trigger_offset_days,
        }
        for ms in sorted(
            default_project.milestones if default_project else [],
            key=lambda item: (item.sequence_order, str(item.id)),
        )
    ]
    # v3: draw schedule sources (scenario-level, linked to capital modules).
    draw_sources = [
        DrawSourceRead.model_validate(source).model_dump(mode="json")
        for source in sorted(
            model.draw_sources, key=lambda item: (item.sort_order, str(item.id))
        )
    ]
    cash_flows = [
        CashFlowRead.model_validate(cash_flow).model_dump(mode="json")
        for cash_flow in sorted(model.cash_flows, key=lambda item: item.period)
    ]
    capital_modules = [
        CapitalModuleRead.model_validate(module).model_dump(mode="json")
        for module in sorted(model.capital_modules, key=lambda item: (item.stack_position, item.label or ""))
    ]
    waterfall_tiers = [
        WaterfallTierRead.model_validate(tier).model_dump(mode="json")
        for tier in sorted(model.waterfall_tiers, key=lambda item: (item.priority, str(item.id)))
    ]
    waterfall_results = [
        WaterfallResultRead.model_validate(result).model_dump(mode="json")
        for result in sorted(model.waterfall_results, key=lambda item: (item.period, str(item.id)))
    ]

    deal_model_payload = ScenarioRead.model_validate(model).model_dump(mode="json")
    deal_model_payload.update(
        {
            "operational_inputs": operational_inputs,
            "income_streams": income_streams,
            "expense_lines": expense_lines,
            "unit_mix": unit_mix,
            "capital_stack": capital_modules,
            "waterfall_tiers": waterfall_tiers,
        }
    )

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "deal",
        "exported_at": datetime.now(UTC).isoformat(),
        "source": {
            "model_id": str(model.id),
            "opportunity_id": str(opportunity_id) if opportunity_id else None,
        },
        "project": _build_project_payload(opportunity),
        "deal_model": deal_model_payload,
        "outputs": outputs,
        "cash_flows": cash_flows,
        "operational_inputs": operational_inputs,
        "operational_outputs": outputs,
        "income_streams": income_streams,
        "expense_lines": expense_lines,
        "use_lines": use_lines,
        "unit_mix": unit_mix,
        "milestones": milestones,
        "capital_modules": capital_modules,
        "waterfall_tiers": waterfall_tiers,
        "waterfall_results": waterfall_results,
        "draw_sources": draw_sources,
    }


__all__ = ["EXPORT_SCHEMA_VERSION", "export_deal_model_json"]
