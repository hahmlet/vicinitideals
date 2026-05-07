"""Parcel and ParcelTransformation models.

ProjectParcel (project_parcels) was a junction table linking the old Opportunity
to parcels. Dropped in migration 0067 — projects now get a direct parcel_id FK.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProjectParcelRelationship(str, enum.Enum):
    unchanged = "unchanged"
    merged_in = "merged_in"
    split_from = "split_from"


class ProjectParcel:
    """Non-ORM stub. project_parcels table dropped in migration 0067.
    Kept for import compatibility — cannot be used in select() or session.add()."""

    project_id: "uuid.UUID"
    parcel_id: "uuid.UUID"
    relationship_type: "ProjectParcelRelationship"
    notes: "str | None"

    def __init__(self, **_: object) -> None:
        pass


class ParcelTransformationType(str, enum.Enum):
    lot_merger = "lot_merger"
    parcel_split = "parcel_split"
    lot_line_adjustment = "lot_line_adjustment"
    no_change = "no_change"


class Parcel(Base):
    __tablename__ = "parcels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    apn: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    apn_normalized: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    address_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_mailing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_street: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    owner_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    gis_acres: Mapped[object | None] = mapped_column(Numeric(18, 8), nullable=True)
    zoning_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zoning_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_use: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assessed_value_land: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    assessed_value_improvements: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    total_assessed_value: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    legal_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
    county: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    priority_bucket: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    latitude: Mapped[object | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[object | None] = mapped_column(Numeric(10, 7), nullable=True)
    postal_city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    unincorporated_community: Mapped[str | None] = mapped_column(String(120), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    building_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_residential: Mapped[bool | None] = mapped_column(nullable=True)
    is_mailable: Mapped[bool | None] = mapped_column(nullable=True)
    address_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    place_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    landmark_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_placement: Mapped[str | None] = mapped_column(String(50), nullable=True)
    elevation_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address_source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    address_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    address_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nguid: Mapped[str | None] = mapped_column(String(200), nullable=True)
    discrepancy_agency_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    esn: Mapped[str | None] = mapped_column(String(50), nullable=True)
    msag_community: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_date: Mapped[str | None] = mapped_column(String(6), nullable=True)
    state_class: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    ortaxlot: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    primary_account_num: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alt_account_num: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rlis_land_use: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rlis_taxcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zoning_lookup_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enterprise_zone_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    cultural_sensitivity: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ParcelTransformation(Base):
    __tablename__ = "parcel_transformations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    transformation_type: Mapped[ParcelTransformationType] = mapped_column(
        String(50), nullable=False
    )
    input_apns: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=False,
    )
    output_apns: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=True,
    )
    effective_lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date: Mapped[object | None] = mapped_column(Date, nullable=True)

    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="parcel_transformations"
    )
