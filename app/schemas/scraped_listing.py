"""Pydantic schemas for rich scraped listings."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator


class ScrapedListingBase(BaseModel):
    source: str
    source_id: str | None = None
    source_url: str | None = None
    listing_url: str | None = None

    address_raw: str | None = None
    address_normalized: str | None = None
    street: str | None = None
    street2: str | None = None
    address: str | None = None
    city: str | None = None
    county: str | None = None
    state_code: str | None = None
    zip_code: str | None = None
    full_address: str | None = None
    lat: Decimal | None = None
    lng: Decimal | None = None

    property_type: str | None = None
    sub_type: list[str] | None = None
    investment_type: str | None = None
    investment_sub_type: str | None = None
    asking_price: Decimal | None = None
    price_per_sqft: Decimal | None = None
    price_per_unit: Decimal | None = None
    price_per_sqft_land: Decimal | None = None
    gba_sqft: Decimal | None = None
    building_sqft: Decimal | None = None
    net_rentable_sqft: Decimal | None = None
    lot_sqft: Decimal | None = None
    year_built: int | None = None
    year_renovated: int | None = None
    units: int | None = None
    unit_count: int | None = None
    buildings: int | None = None
    stories: int | None = None
    parking_spaces: int | None = None
    pads: int | None = None
    number_of_keys: int | None = None
    class_: str | None = None
    zoning: str | None = None
    apn: str | None = None
    occupancy_pct: Decimal | None = None
    occupancy_date: datetime | None = None
    tenancy: str | None = None
    cap_rate: Decimal | None = None
    asking_cap_rate_pct: Decimal | None = None
    proforma_cap_rate: Decimal | None = None
    noi: Decimal | None = None
    proforma_noi: Decimal | None = None
    lease_term: Decimal | None = None
    lease_commencement: datetime | None = None
    lease_expiration: datetime | None = None
    remaining_term: Decimal | None = None
    rent_bumps: str | None = None
    sale_condition: str | None = None
    broker_co_op: bool = False
    ownership: str | None = None
    is_in_opportunity_zone: bool | None = None

    listing_name: str | None = None
    description: str | None = None
    parsed_description: dict | None = None
    status: str | None = None
    raw_json: dict | None = None

    @model_validator(mode="after")
    def _sync_compatibility_fields(self) -> "ScrapedListingBase":
        if self.source_url is None and self.listing_url is not None:
            self.source_url = self.listing_url
        if self.listing_url is None and self.source_url is not None:
            self.listing_url = self.source_url
        if self.street is None and self.address is not None:
            self.street = self.address
        if self.address is None and self.street is not None:
            self.address = self.street
        if self.units is None and self.unit_count is not None:
            self.units = self.unit_count
        if self.unit_count is None and self.units is not None:
            self.unit_count = self.units
        if self.full_address is None and self.street is not None:
            street_line = self.street.strip()
            if self.street2:
                street_line = f"{street_line} {self.street2.strip()}"
            parts = [street_line]
            if self.city:
                parts.append(self.city.strip())
            if self.state_code or self.zip_code:
                tail = " ".join(part.strip() for part in [self.state_code, self.zip_code] if part)
                if tail:
                    parts.append(tail)
            self.full_address = ", ".join(parts) if parts else None
        if self.cap_rate is None and self.asking_cap_rate_pct is not None:
            self.cap_rate = self.asking_cap_rate_pct
        if self.asking_cap_rate_pct is None and self.cap_rate is not None:
            self.asking_cap_rate_pct = self.cap_rate
        if self.building_sqft is None and self.gba_sqft is not None:
            self.building_sqft = self.gba_sqft
        if self.gba_sqft is None and self.building_sqft is not None:
            self.gba_sqft = self.building_sqft
        return self


class ScrapedListingCreate(ScrapedListingBase):
    ingest_job_id: uuid.UUID | None = None
    broker_id: uuid.UUID | None = None
    parcel_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    linked_project_id: uuid.UUID | None = None


class ScrapedListingUpsert(ScrapedListingCreate):
    pass


class ScrapedListingRead(ScrapedListingBase):
    id: uuid.UUID
    ingest_job_id: uuid.UUID | None = None
    broker_id: uuid.UUID | None = None
    parcel_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    linked_project_id: uuid.UUID | None = None
    listed_at: datetime | None = None
    updated_at_source: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    is_new: bool = True
    matches_saved_criteria: bool = False
    canonical_id: uuid.UUID | None = None

    # Parcel reconciliation
    jurisdiction: str | None = None
    match_strategy: str | None = None
    match_confidence: float | None = None
    lot_size_mismatch: bool | None = None

    model_config = {"from_attributes": True}
