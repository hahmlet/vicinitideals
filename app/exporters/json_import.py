"""Validation and import helpers for portable deal-model JSON payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.json_export import EXPORT_SCHEMA_VERSION
from app.models.deal import Deal, Scenario, IncomeStream, OperatingExpenseLine, OperationalInputs
from app.models.project import Opportunity, Project, ProjectCategory, ProjectSource, ProjectStatus
from app.schemas.capital import CapitalModuleBase, DrawSourceBase, WaterfallTierBase
from app.schemas.deal import (
    ScenarioBase,
    ScenarioRead,
    IncomeStreamBase,
    OperatingExpenseLineBase,
    OperationalInputsBase,
    UnitMixBase,
    UseLineBase,
)
from app.schemas.project import ProjectRead
from app.services.deal_restore import (
    restore_capital_modules,
    restore_draw_sources,
    restore_milestones,
    restore_use_lines,
    restore_waterfall_tiers,
)

DEAL_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Deal JSON Export Schema",
    "type": "object",
    "required": ["schema_version", "project", "deal_model"],
    "properties": {
        "schema_version": {
            "type": "string",
            "enum": [EXPORT_SCHEMA_VERSION, "deal-json-v2", "deal-json-v1"],
        },
        "export_type": {"type": "string", "default": "deal"},
        "project": {
            "type": "object",
            "properties": {
                "Name": {"type": ["string", "null"]},
                "UnparsedAddress": {"type": ["string", "null"]},
                "City": {"type": ["string", "null"]},
                "StateOrProvince": {"type": ["string", "null"]},
                "PostalCode": {"type": ["string", "null"]},
                "ParcelNumber": {"type": ["string", "null"]},
                "LotSizeSquareFeet": {"type": ["number", "string", "null"]},
                "YearBuilt": {"type": ["integer", "null"]},
                "BuildingAreaTotal": {"type": ["number", "string", "null"]},
                "PropertyType": {"type": ["string", "null"]},
            },
        },
        "deal_model": {
            "type": "object",
            "required": ["name", "project_type"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "integer"},
                "is_active": {"type": "boolean"},
                "project_type": {"type": "string"},
                "operational_inputs": {"type": ["object", "null"]},
                "income_streams": {"type": "array"},
                "expense_lines": {"type": "array"},
                "capital_stack": {"type": "array"},
                "waterfall_tiers": {"type": "array"},
            },
        },
        "operational_inputs": {"type": ["object", "null"]},
        "income_streams": {"type": "array"},
        "expense_lines": {"type": "array"},
        "use_lines": {"type": "array"},
        "unit_mix": {"type": "array"},
        "milestones": {"type": "array"},
        "capital_modules": {"type": "array"},
        "waterfall_tiers": {"type": "array"},
        "draw_sources": {"type": "array"},
        "outputs": {"type": ["object", "null"]},
        "cash_flows": {"type": "array"},
    },
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None:
        return None
    return value


class CapitalModuleImportData(CapitalModuleBase):
    id: UUID | None = None


class WaterfallTierImportData(WaterfallTierBase):
    id: UUID | None = None


class UseLineImportData(UseLineBase):
    id: UUID | None = None


class DrawSourceImportData(DrawSourceBase):
    id: UUID | None = None


class MilestoneImportData(BaseModel):
    """One exported milestone row (v3). ``id`` is the stable key that
    ``trigger_milestone_id`` chains reference; import re-creates rows with
    new UUIDs and rewires the chains via the old→new map."""

    model_config = {"extra": "ignore"}

    id: UUID | None = None
    milestone_type: str
    duration_days: int = 0
    target_date: date | None = None
    sequence_order: int = 1
    label: str | None = None
    trigger_milestone_id: UUID | None = None
    trigger_offset_days: int = 0


class DealProjectData(BaseModel):
    Name: str | None = None
    UnparsedAddress: str | None = None
    City: str | None = None
    StateOrProvince: str | None = None
    PostalCode: str | None = None
    ParcelNumber: str | None = None
    LotSizeSquareFeet: Decimal | None = None
    YearBuilt: int | None = None
    BuildingAreaTotal: Decimal | None = None
    PropertyType: str | None = None
    Status: Optional[ProjectStatus] = ProjectStatus.active
    ProjectCategory: Optional[ProjectCategory] = ProjectCategory.proposed
    Source: Optional[ProjectSource] = ProjectSource.manual

    model_config = {"extra": "allow"}


class DealImportPayload(BaseModel):
    schema_version: str
    project: DealProjectData | None = None
    deal_model: ScenarioBase
    operational_inputs: OperationalInputsBase | None = None
    income_streams: list[IncomeStreamBase] = Field(default_factory=list)
    expense_lines: list[OperatingExpenseLineBase] = Field(default_factory=list)
    capital_modules: list[CapitalModuleImportData] = Field(default_factory=list)
    waterfall_tiers: list[WaterfallTierImportData] = Field(default_factory=list)
    # ── deal-json-v3 blocks (absent from v1/v2 payloads → empty defaults) ──
    use_lines: list[UseLineImportData] = Field(default_factory=list)
    milestones: list[MilestoneImportData] = Field(default_factory=list)
    draw_sources: list[DrawSourceImportData] = Field(default_factory=list)
    # unit_mix rows are free-form JSONB dicts on Project; validated through
    # UnitMixBase at persist time (invalid rows are skipped with a warning).
    unit_mix: list[dict] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_structure(cls, raw_value: Any) -> Any:
        if not isinstance(raw_value, Mapping):
            return raw_value

        data = dict(raw_value)
        deal_model_data = data.get("deal_model")
        if isinstance(deal_model_data, Mapping):
            deal_model_mapping = dict(deal_model_data)
            for source_key, target_key in (
                ("operational_inputs", "operational_inputs"),
                ("income_streams", "income_streams"),
                ("expense_lines", "expense_lines"),
                ("operating_expense_lines", "expense_lines"),
                ("capital_stack", "capital_modules"),
                ("capital_modules", "capital_modules"),
                ("waterfall_tiers", "waterfall_tiers"),
                ("use_lines", "use_lines"),
                ("milestones", "milestones"),
                ("draw_sources", "draw_sources"),
                ("unit_mix", "unit_mix"),
            ):
                if target_key not in data and source_key in deal_model_mapping:
                    data[target_key] = deal_model_mapping[source_key]

            data["deal_model"] = {
                key: value
                for key, value in deal_model_mapping.items()
                if key in ScenarioBase.model_fields
            }

        return data


class DealImportValidationResult(BaseModel):
    valid: bool
    schema_version: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class DealImportResult(BaseModel):
    model: ScenarioRead
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DealPayloadImportResult(BaseModel):
    project: ProjectRead
    model: ScenarioRead
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def _build_counts(payload: DealImportPayload) -> dict[str, int]:
    return {
        "income_streams": len(payload.income_streams),
        "capital_modules": len(payload.capital_modules),
        "waterfall_tiers": len(payload.waterfall_tiers),
        "expense_lines": len(payload.expense_lines),
        "use_lines": len(payload.use_lines),
        "milestones": len(payload.milestones),
        "draw_sources": len(payload.draw_sources),
        "unit_mix": len(payload.unit_mix),
    }


def validate_deal_import_payload(payload: Mapping[str, Any]) -> DealImportValidationResult:
    """Validate an incoming portable payload without mutating the database."""
    errors: list[str] = []
    warnings: list[str] = []
    schema_version = payload.get("schema_version") if isinstance(payload, Mapping) else None

    # Accept the current version plus v2 and v1 for backward compatibility.
    # Older exports simply lack the newer fields/blocks — Pydantic treats
    # them as None / empty defaults when parsing.
    _SUPPORTED_VERSIONS = {EXPORT_SCHEMA_VERSION, "deal-json-v2", "deal-json-v1"}
    if schema_version not in _SUPPORTED_VERSIONS:
        errors.append(
            f"Unsupported schema_version '{schema_version}'. "
            f"Expected one of: {sorted(_SUPPORTED_VERSIONS)}."
        )
    elif schema_version == "deal-json-v1":
        warnings.append(
            "Importing a pre-Phase-B (v1) export. Phase B fields "
            "(debt_types, debt_terms, debt_sizing_mode, etc.) will be "
            "absent; re-run the deal setup wizard to populate them."
        )

    try:
        parsed = DealImportPayload.model_validate(payload)
    except ValidationError as exc:
        errors.extend(
            f"{'/'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return DealImportValidationResult(
            valid=False,
            schema_version=str(schema_version) if schema_version is not None else None,
            errors=errors,
            warnings=warnings,
        )

    if parsed.project is None:
        warnings.append("Project metadata is missing; /deals/import will derive the project name from the deal model.")
    if not parsed.income_streams:
        warnings.append("No income streams were supplied; compute endpoints may return empty revenue results.")
    if parsed.capital_modules and not parsed.waterfall_tiers:
        warnings.append("Capital modules were provided without waterfall tiers; waterfall outputs will be limited.")

    return DealImportValidationResult(
        valid=not errors,
        schema_version=parsed.schema_version,
        errors=errors,
        warnings=warnings,
        counts=_build_counts(parsed),
    )


async def import_deal_model_json(
    session: AsyncSession,
    *,
    project_id: UUID,
    payload: Mapping[str, Any],
    created_by_user_id: UUID | None = None,
) -> DealImportResult:
    """Create a new deal model and nested records from an exported JSON payload."""
    validation = validate_deal_import_payload(payload)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))

    parsed = DealImportPayload.model_validate(payload)

    # Find or create top-level Deal linked to this Opportunity (via Project)
    existing_top_deal = (await session.execute(
        select(Deal)
        .join(Scenario, Scenario.deal_id == Deal.id)
        .join(Project, Project.scenario_id == Scenario.id)
        .where(Project.opportunity_id == project_id)
        .limit(1)
    )).scalar_one_or_none()
    if existing_top_deal is None:
        deal_name = parsed.deal_model.name or "Imported Deal"
        existing_top_deal = Deal(
            org_id=(await session.execute(
                select(Opportunity.org_id).where(Opportunity.id == project_id)
            )).scalar_one(),
            name=deal_name,
            created_by_user_id=created_by_user_id,
        )
        session.add(existing_top_deal)
        await session.flush()

    model = Scenario(
        deal_id=existing_top_deal.id,
        created_by_user_id=created_by_user_id,
        **parsed.deal_model.model_dump(exclude_unset=True),
    )
    session.add(model)
    await session.flush()

    # Create the default dev Project bridging this Scenario to the Opportunity
    dev_project = Project(
        scenario_id=model.id,
        opportunity_id=project_id,
        name="Default Project",
    )
    session.add(dev_project)
    await session.flush()

    if parsed.operational_inputs is not None:
        inputs_payload = parsed.operational_inputs.model_dump(exclude_unset=True)
        if "milestone_dates" in inputs_payload:
            inputs_payload["milestone_dates"] = json.loads(json.dumps(_json_safe(inputs_payload["milestone_dates"])))
        session.add(
            OperationalInputs(
                project_id=dev_project.id,
                **inputs_payload,
            )
        )

    for stream in parsed.income_streams:
        session.add(
            IncomeStream(
                project_id=dev_project.id,
                **stream.model_dump(exclude_unset=True),
            )
        )

    for expense_line in parsed.expense_lines:
        session.add(
            OperatingExpenseLine(
                project_id=dev_project.id,
                **expense_line.model_dump(exclude_unset=True),
            )
        )

    warnings = list(validation.warnings)

    def _dump_with_id(item: BaseModel) -> dict[str, Any]:
        """JSON-safe dump preserving unset-ness, with the stable id restored."""
        data = item.model_dump(mode="json", exclude_unset=True)
        item_id = getattr(item, "id", None)
        if item_id is not None:
            data["id"] = str(item_id)
        return data

    # unit_mix is JSONB on Project — validate rows and skip anything broken.
    # Dump in python mode + _json_safe so Decimals land as JSON numbers, not
    # strings (mode="json" stringifies Decimal, which drifts on re-export).
    restored_mix: list[dict] = []
    for mix_data in parsed.unit_mix:
        try:
            restored_mix.append(
                _json_safe(
                    UnitMixBase.model_validate(mix_data).model_dump(
                        exclude_unset=True
                    )
                )
            )
        except ValidationError:
            warnings.append("Skipped one unit_mix row that failed validation.")
    if restored_mix:
        dev_project.unit_mix = restored_mix

    # v3 blocks — shared restore helpers handle the old→new ID remapping:
    # milestones first (trigger chains), then capital modules (milestone
    # anchors), then use lines (eligible_module_ids + milestone FKs), then
    # draw sources and waterfall tiers (capital module + project FKs).
    milestone_id_map = await restore_milestones(
        session,
        project_id=dev_project.id,
        milestone_payloads=[_dump_with_id(ms) for ms in parsed.milestones],
        log_context="deal import",
        strict=True,
    )

    capital_module_id_map, _ = await restore_capital_modules(
        session,
        scenario_id=model.id,
        module_payloads=[_dump_with_id(m) for m in parsed.capital_modules],
        milestone_id_map=milestone_id_map,
        log_context="deal import",
        strict=True,
    )

    await restore_use_lines(
        session,
        project_id=dev_project.id,
        use_line_payloads=[_dump_with_id(u) for u in parsed.use_lines],
        cap_id_map=capital_module_id_map,
        milestone_id_map=milestone_id_map,
        log_context="deal import",
        strict=True,
    )

    await restore_draw_sources(
        session,
        scenario_id=model.id,
        draw_source_payloads=[_dump_with_id(ds) for ds in parsed.draw_sources],
        cap_id_map=capital_module_id_map,
        default_project_id=dev_project.id,
        log_context="deal import",
        strict=True,
        on_missing_capital_module="error",
    )

    await restore_waterfall_tiers(
        session,
        scenario_id=model.id,
        tier_payloads=[_dump_with_id(t) for t in parsed.waterfall_tiers],
        cap_id_map=capital_module_id_map,
        default_project_id=dev_project.id,
        log_context="deal import",
        strict=True,
        on_missing_capital_module="error",
    )

    await session.flush()
    await session.refresh(model)

    return DealImportResult(
        model=ScenarioRead.model_validate(model),
        counts=_build_counts(parsed),
        warnings=warnings,
    )


async def import_deal_from_json(
    session: AsyncSession,
    *,
    org_id: UUID,
    payload: Mapping[str, Any],
    created_by_user_id: UUID | None = None,
) -> DealPayloadImportResult:
    """Create a project from the payload and import the nested deal model into it."""
    validation = validate_deal_import_payload(payload)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))

    parsed = DealImportPayload.model_validate(payload)
    project_meta = parsed.project or DealProjectData()
    project_name = (
        project_meta.Name
        or project_meta.UnparsedAddress
        or (project_meta.ParcelNumber and f"Parcel {project_meta.ParcelNumber}")
        or parsed.deal_model.name
    )

    # NB: use .value, not str() — str() on a (str, Enum) mixin yields
    # "OpportunitySource.manual", which is not a valid column value and made
    # ProjectRead validation reject every imported project.
    def _enum_value(value: Any, default: str) -> str:
        if value is None:
            return default
        return value.value if isinstance(value, Enum) else str(value)

    opportunity = Opportunity(
        org_id=org_id,
        name=project_name,
        opp_status=_enum_value(project_meta.Status, ProjectStatus.active.value),
        project_category=_enum_value(
            project_meta.ProjectCategory, ProjectCategory.proposed.value
        ),
        source=_enum_value(project_meta.Source, ProjectSource.manual.value),
        source_url="",  # manual entry
        created_by_user_id=created_by_user_id,
    )
    session.add(opportunity)
    await session.flush()

    parcel_number = (project_meta.ParcelNumber or "").strip().upper()
    if parcel_number:
        opportunity.apn = parcel_number
        if project_meta.UnparsedAddress:
            opportunity.address_normalized = project_meta.UnparsedAddress
            opportunity.address_raw = project_meta.UnparsedAddress
        if project_meta.LotSizeSquareFeet is not None:
            opportunity.lot_sqft = project_meta.LotSizeSquareFeet
        if project_meta.YearBuilt is not None:
            opportunity.year_built = project_meta.YearBuilt
        if project_meta.BuildingAreaTotal is not None:
            opportunity.gba_sqft = project_meta.BuildingAreaTotal
        if project_meta.PropertyType:
            opportunity.property_type = project_meta.PropertyType
        await session.flush()

    model_result = await import_deal_model_json(
        session=session,
        project_id=opportunity.id,
        payload=payload,
        created_by_user_id=created_by_user_id,
    )
    await session.refresh(opportunity)

    return DealPayloadImportResult(
        project=ProjectRead.model_validate(opportunity),
        model=model_result.model,
        counts=model_result.counts,
        warnings=model_result.warnings,
    )


__all__ = [
    "DEAL_JSON_SCHEMA",
    "DealImportResult",
    "DealImportValidationResult",
    "DealPayloadImportResult",
    "import_deal_from_json",
    "import_deal_model_json",
    "validate_deal_import_payload",
]
