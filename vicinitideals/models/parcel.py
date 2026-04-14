"""Parcel, ProjectParcel, ParcelTransformation models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vicinitideals.models.base import Base


class ProjectParcelRelationship(str, enum.Enum):
    unchanged = "unchanged"
    merged_in = "merged_in"
    split_from = "split_from"


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

    # Location routing (populated from Oregon Address Points / county scrapers)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    # Priority classification
    priority_bucket: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)

    # Oregon Address Points fields (populated at seed time, quarterly refresh)
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

    # Metro RLIS taxlot fields (populated from tax_lots_metro_rlis cache)
    sale_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_date: Mapped[str | None] = mapped_column(String(6), nullable=True)  # YYYYMM
    state_class: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    ortaxlot: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    primary_account_num: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alt_account_num: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rlis_land_use: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rlis_taxcode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # For jurisdictions with no queryable GIS zoning layer — links to an authoritative PDF
    # zoning map. Populated at seed time when jurisdiction is in ZONING_PDF_JURISDICTIONS
    # and zoning_code is null. See tools/gis_cache/oregon_statewide_sources.py.
    zoning_lookup_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Enterprise zone name (e.g. "Columbia Cascade Enterprise Zone").
    # Populated by spatial join against enterprise_zones_or cache at seed time.
    # NULL = not in any enterprise zone.
    enterprise_zone_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    # Cultural sensitivity designation — manually painted via zone painter.
    # NULL = not designated. Value = designation label (e.g. "Cultural Sensitivity Lands").
    cultural_sensitivity: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Relationships
    project_parcels: Mapped[list["ProjectParcel"]] = relationship(
        "ProjectParcel", back_populates="parcel"
    )


class ProjectParcel(Base):
    __tablename__ = "project_parcels"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id"),
        primary_key=True,
    )
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parcels.id"),
        primary_key=True,
    )
    relationship_type: Mapped[ProjectParcelRelationship] = mapped_column(
        "relationship",
        String(50),
        nullable=False,
        default=ProjectParcelRelationship.unchanged,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    parcel: Mapped["Parcel"] = relationship("Parcel", back_populates="project_parcels")
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="project_parcels"
    )


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
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    output_apns: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    effective_lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date: Mapped[object | None] = mapped_column(Date, nullable=True)

    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="parcel_transformations"
    )
