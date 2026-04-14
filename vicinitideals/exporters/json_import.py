"""Validation and import helpers for portable deal-model JSON payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vicinitideals.exporters.json_export import EXPORT_SCHEMA_VERSION
from vicinitideals.models.capital import CapitalModule, WaterfallTier
from vicinitideals.models.deal import Deal, DealModel, DealOpportunity, IncomeStream, OperatingExpenseLine, OperationalInputs
from vicinitideals.models.parcel import Parcel, ProjectParcel, ProjectParcelRelationship
from vicinitideals.models.project import Opportunity, Project, ProjectCategory, ProjectSource, ProjectStatus
from vicinitideals.schemas.capital import CapitalModuleBase, WaterfallTierBase
from vicinitideals.schemas.deal import (
    DealModelBase,
    DealModelRead,
    IncomeStreamBase,
    OperatingExpenseLineBase,
    OperationalInputsBase,
)
from vicinitideals.schemas.project import ProjectRead

DEAL_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Deal JSON Export Schema",
    "type": "object",
    "required": ["schema_version", "project", "deal_model"],
    "properties": {
        "schema_version": {"type": "string", "const": EXPORT_SCHEMA_VERSION},
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
        "capital_modules": {"type": "array"},
        "waterfall_tiers": {"type": "array"},
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
    Status: ProjectStatus = ProjectStatus.active
    ProjectCategory: ProjectCategory = ProjectCategory.proposed
    Source: ProjectSource = ProjectSource.manual

    model_config = {"extra": "allow"}


class DealImportPayload(BaseModel):
    schema_version: str
    project: DealProjectData | None = None
    deal_model: DealModelBase
    operational_inputs: OperationalInputsBase | None = None
    income_streams: list[IncomeStreamBase] = Field(default_factory=list)
    expense_lines: list[OperatingExpenseLineBase] = Field(default_factory=list)
    capital_modules: list[CapitalModuleImportData] = Field(default_factory=list)
    waterfall_tiers: list[WaterfallTierImportData] = Field(default_factory=list)

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
            ):
                if target_key not in data and source_key in deal_model_mapping:
                    data[target_key] = deal_model_mapping[source_key]

            data["deal_model"] = {
                key: value
                for key, value in deal_model_mapping.items()
                if key in DealModelBase.model_fields
            }

        return data


class DealImportValidationResult(BaseModel):
    valid: bool
    schema_version: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class DealImportResult(BaseModel):
    model: DealModelRead
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DealPayloadImportResult(BaseModel):
    project: ProjectRead
    model: DealModelRead
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def _build_counts(payload: DealImportPayload) -> dict[str, int]:
    return {
        "income_streams": len(payload.income_streams),
        "capital_modules": len(payload.capital_modules),
        "waterfall_tiers": len(payload.waterfall_tiers),
    }


def validate_deal_import_payload(payload: Mapping[str, Any]) -> DealImportValidationResult:
    """Validate an incoming portable payload without mutating the database."""
    errors: list[str] = []
    warnings: list[str] = []
    schema_version = payload.get("schema_version") if isinstance(payload, Mapping) else None

    if schema_version != EXPORT_SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema_version '{schema_version}'. Expected '{EXPORT_SCHEMA_VERSION}'."
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

    # Find or create top-level Deal linked to this Opportunity
    existing_top_deal = (await session.execute(
        select(Deal).join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
        .where(DealOpportunity.opportunity_id == project_id).limit(1)
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
        session.add(DealOpportunity(deal_id=existing_top_deal.id, opportunity_id=project_id))
        await session.flush()

    model = DealModel(
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
        deal_type=str(getattr(model.project_type, "value", model.project_type)),
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

    capital_module_id_map: dict[UUID, UUID] = {}
    for capital_module in parsed.capital_modules:
        module = CapitalModule(
            scenario_id=model.id,
            **_json_safe(capital_module.model_dump(exclude={"id"}, exclude_unset=True)),
        )
        session.add(module)
        await session.flush()
        if capital_module.id is not None:
            capital_module_id_map[capital_module.id] = module.id

    for waterfall_tier in parsed.waterfall_tiers:
        tier_payload = waterfall_tier.model_dump(exclude={"id"}, exclude_unset=True)
        if waterfall_tier.capital_module_id is not None:
            remapped_capital_id = capital_module_id_map.get(waterfall_tier.capital_module_id)
            if remapped_capital_id is None:
                raise ValueError(
                    "waterfall_tiers references a capital_module_id that is not present in the import payload"
                )
            tier_payload["capital_module_id"] = remapped_capital_id

        session.add(WaterfallTier(scenario_id=model.id, **tier_payload))

    await session.flush()
    await session.refresh(model)

    return DealImportResult(
        model=DealModelRead.model_validate(model),
        counts=_build_counts(parsed),
        warnings=validation.warnings,
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

    opportunity = Opportunity(
        org_id=org_id,
        name=project_name,
        status=project_meta.Status,
        project_category=project_meta.ProjectCategory,
        source=project_meta.Source,
        created_by_user_id=created_by_user_id,
    )
    session.add(opportunity)
    await session.flush()

    parcel_number = (project_meta.ParcelNumber or "").strip().upper()
    if parcel_number:
        parcel = (
            await session.execute(select(Parcel).where(Parcel.apn == parcel_number))
        ).scalar_one_or_none()
        if parcel is None:
            parcel = Parcel(apn=parcel_number)
            session.add(parcel)

        if project_meta.UnparsedAddress:
            parcel.address_normalized = project_meta.UnparsedAddress
            parcel.address_raw = project_meta.UnparsedAddress
        if project_meta.LotSizeSquareFeet is not None:
            parcel.lot_sqft = project_meta.LotSizeSquareFeet
        if project_meta.YearBuilt is not None:
            parcel.year_built = project_meta.YearBuilt
        if project_meta.BuildingAreaTotal is not None:
            parcel.building_sqft = project_meta.BuildingAreaTotal
        if project_meta.PropertyType:
            parcel.current_use = project_meta.PropertyType

        await session.flush()
        session.add(
            ProjectParcel(
                project_id=opportunity.id,
                parcel_id=parcel.id,
                relationship_type=ProjectParcelRelationship.unchanged,
            )
        )
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
