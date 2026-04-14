"""Parcel, ProjectParcel, ParcelTransformation schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from vicinitideals.models.parcel import ParcelTransformationType, ProjectParcelRelationship


# ---------------------------------------------------------------------------
# Parcel
# ---------------------------------------------------------------------------

class ParcelBase(BaseModel):
    apn: str
    address_normalized: str | None = None
    address_raw: str | None = None
    state_id: str | None = None
    owner_name: str | None = None
    owner_mailing_address: str | None = None
    owner_street: str | None = None
    owner_city: str | None = None
    owner_state: str | None = None
    owner_zip: str | None = None
    lot_sqft: Decimal | None = None
    gis_acres: Decimal | None = None
    zoning_code: str | None = None
    zoning_description: str | None = None
    current_use: str | None = None
    assessed_value_land: Decimal | None = None
    assessed_value_improvements: Decimal | None = None
    total_assessed_value: Decimal | None = None
    tax_code: str | None = None
    legal_description: str | None = None
    year_built: int | None = None
    building_sqft: Decimal | None = None
    unit_count: int | None = None
    geometry: dict | None = None


class ParcelCreate(ParcelBase):
    pass


class ParcelRead(ParcelBase):
    id: uuid.UUID
    scraped_at: datetime | None = None
    last_updated: datetime | None = None

    model_config = {"from_attributes": True}


class ParcelLookupRequest(BaseModel):
    addresses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_addresses(self) -> "ParcelLookupRequest":
        cleaned = [" ".join(address.split()).upper() for address in self.addresses if address and address.strip()]
        if not cleaned:
            raise ValueError("`addresses` must contain at least one non-empty address.")
        self.addresses = cleaned
        return self


class GreshamLookupParcel(BaseModel):
    state_id: str | None = None
    rno: str | None = None
    site_address: str | None = None
    owner_name: str | None = None
    owner_street: str | None = None
    owner_city: str | None = None
    owner_state: str | None = None
    owner_zip: str | None = None
    zone: str | None = None
    land_use: str | None = None
    gis_acres: Decimal | None = None
    sqft: Decimal | None = None
    building_sqft: Decimal | None = None
    year_built: int | None = None
    land_value: Decimal | None = None
    building_value: Decimal | None = None
    total_value: Decimal | None = None
    tax_code: str | None = None
    legal_description: str | None = None
    geometry: dict[str, Any] | None = None


class ParcelLookupResult(BaseModel):
    input_address: str
    match_status: Literal["single_match", "multiple_matches", "no_match"]
    parcels: list[GreshamLookupParcel] = Field(default_factory=list)


class ParcelLookupResponse(BaseModel):
    results: list[ParcelLookupResult] = Field(default_factory=list)


class ClackamasLookupRequest(BaseModel):
    address: str

    @model_validator(mode="after")
    def _validate_address(self) -> "ClackamasLookupRequest":
        if not self.address.strip():
            raise ValueError("`address` is required for Clackamas lookup.")
        return self


class OregonCityLookupRequest(BaseModel):
    address: str

    @model_validator(mode="after")
    def _validate_address(self) -> "OregonCityLookupRequest":
        if not self.address.strip():
            raise ValueError("`address` is required for Oregon City lookup.")
        return self


class PortlandLookupRequest(BaseModel):
    address: str

    @model_validator(mode="after")
    def _validate_address(self) -> "PortlandLookupRequest":
        if not self.address.strip():
            raise ValueError("`address` is required for Portland lookup.")
        return self


class PortlandCoordinates(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class PortlandParcelIds(BaseModel):
    address_id: str | None = None
    state_id: str | None = None
    tlid: str | None = None
    property_id: str | None = None
    county_property_id: str | None = None


class PortlandMailingAddress(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


class PortlandLotMetrics(BaseModel):
    acreage: Decimal | None = None
    lot_sqft: Decimal | None = None


class PortlandValuation(BaseModel):
    land: Decimal | None = None
    improvements: Decimal | None = None
    total: Decimal | None = None


class PortlandZoningContext(BaseModel):
    code: str | None = None
    description: str | None = None
    comp_plan: str | None = None
    overlays: list[str] = Field(default_factory=list)
    plan_district: str | None = None


class PortlandHazardFlags(BaseModel):
    liquefaction: bool | None = None
    floodway: bool | None = None
    flood_hazard: bool | None = None


class PortlandBuildingDetails(BaseModel):
    use: str | None = None
    stories: Decimal | None = None
    sqft: Decimal | None = None
    year_built: int | None = None
    height_ft: Decimal | None = None


class ClackamasParcelResult(BaseModel):
    input_address: str
    match_status: Literal["single_match", "no_match"]
    primary_address: str | None = None
    jurisdiction: str | None = None
    map_number: str | None = None
    taxlot_number: str | None = None
    parcel_number: str | None = None
    document_number: str | None = None
    census_tract: str | None = None
    landclass: str | None = None
    zoning_label: str | None = None
    zoning_value: str | None = None
    zoning_url: str | None = None
    ugb_raw: str | None = None
    ugb_status: Literal["inside", "outside"] | None = None
    flood_hazard: str | None = None
    school_district: str | None = None
    planning_org: str | None = None


class OregonCityParcelResult(BaseModel):
    input_address: str
    match_status: Literal["single_match", "no_match"]
    situs_address: str | None = None
    apn: str | None = None
    parcel_number: str | None = None
    zoning_code: str | None = None
    comp_plan: str | None = None
    in_city: bool | None = None
    ugb_status: Literal["inside", "outside"] | None = None
    gis_acres: Decimal | None = None
    year_built: int | None = None
    living_area_sqft: Decimal | None = None
    total_assessed_value: Decimal | None = None
    sale_price: Decimal | None = None
    sale_date: str | None = None
    flood_hazard: str | None = None


class PortlandParcelResult(BaseModel):
    input_address: str
    match_status: Literal["single_match", "no_match", "ambiguous"]
    address_match: str | None = None
    coordinates: PortlandCoordinates | None = None
    parcel_ids: PortlandParcelIds | None = None
    owner: str | None = None
    mailing_address: PortlandMailingAddress | None = None
    legal_description: str | None = None
    lot_metrics: PortlandLotMetrics | None = None
    valuation: PortlandValuation | None = None
    zoning: PortlandZoningContext | None = None
    neighborhood: str | None = None
    council_district: str | None = None
    business_district: str | None = None
    hazard_flags: PortlandHazardFlags | None = None
    building_details: PortlandBuildingDetails | None = None


# ---------------------------------------------------------------------------
# ProjectParcel
# ---------------------------------------------------------------------------

class ProjectParcelBase(BaseModel):
    relationship_type: ProjectParcelRelationship = ProjectParcelRelationship.unchanged
    notes: str | None = None


class ProjectParcelCreate(ProjectParcelBase):
    project_id: uuid.UUID
    parcel_id: uuid.UUID


class ProjectParcelRead(ProjectParcelBase):
    project_id: uuid.UUID
    parcel_id: uuid.UUID
    parcel: ParcelRead | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ParcelTransformation
# ---------------------------------------------------------------------------

class ParcelTransformationBase(BaseModel):
    transformation_type: ParcelTransformationType
    input_apns: list[str]
    output_apns: list[str] | None = None
    effective_lot_sqft: Decimal | None = None
    notes: str | None = None
    effective_date: date | None = None


class ParcelTransformationCreate(ParcelTransformationBase):
    project_id: uuid.UUID


class ParcelTransformationRead(ParcelTransformationBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = {"from_attributes": True}
