"""Rich scraped-listing ORM model with Crexi/LoopNet field mapping support."""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.models.base import Base


class ScrapedListing(Base):
    __tablename__ = "scraped_listings"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_scraped_listings_source_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ingest_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id"), nullable=True
    )

    # Source identity
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default=lambda: uuid.uuid4().hex
    )
    source_url: Mapped[str] = mapped_column("listing_url", Text, nullable=False)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Location
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    street: Mapped[str | None] = mapped_column(Text, nullable=True)
    street2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lat: Mapped[object | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[object | None] = mapped_column(Numeric(10, 7), nullable=True)

    # Property facts
    property_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sub_type: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    investment_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    investment_sub_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    asking_price: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    price_per_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    price_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    price_per_sqft_land: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    gba_sqft: Mapped[object | None] = mapped_column("building_sqft", Numeric(18, 6), nullable=True)
    net_rentable_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_renovated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units: Mapped[int | None] = mapped_column("unit_count", Integer, nullable=True)
    buildings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking_spaces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_keys: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_: Mapped[str | None] = mapped_column(String(20), nullable=True)
    zoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    apn: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occupancy_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    occupancy_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tenancy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cap_rate: Mapped[object | None] = mapped_column("asking_cap_rate_pct", Numeric(18, 6), nullable=True)
    proforma_cap_rate: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    noi: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    proforma_noi: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lease_term: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lease_commencement: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remaining_term: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    rent_bumps: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_co_op: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ownership: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_in_opportunity_zone: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Listing metadata
    listing_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_description: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column("seen_at", DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        "scraped_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Existing ingestion / review flags retained for backwards compatibility
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matches_saved_criteria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Foreign keys
    broker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokers.id"), nullable=True
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=True
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id"), nullable=True
    )
    linked_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=True
    )

    linked_opportunity: Mapped["Opportunity | None"] = relationship(  # type: ignore[name-defined]
        "Opportunity",
        back_populates="scraped_listings",
        foreign_keys=[linked_project_id],
    )
    ingest_job: Mapped["IngestJob | None"] = relationship(  # type: ignore[name-defined]
        "IngestJob",
        back_populates="scraped_listings",
    )
    broker: Mapped["Broker | None"] = relationship(  # type: ignore[name-defined]
        "Broker",
        back_populates="scraped_listings",
        foreign_keys=[broker_id],
    )
    parcel: Mapped["Parcel | None"] = relationship(  # type: ignore[name-defined]
        "Parcel",
        foreign_keys=[parcel_id],
    )
    building: Mapped["Building | None"] = relationship(  # type: ignore[name-defined]
        "Building",
        foreign_keys=[property_id],
    )

    @builtins.property
    def full_address(self) -> str | None:
        parts = [self.street, self.street2, self.city, self.state_code, self.zip_code]
        pieces = [str(part).strip() for part in parts if part not in (None, "") and str(part).strip()]
        if not pieces:
            return None
        if self.street and self.city and self.state_code and self.zip_code:
            street_line = self.street.strip()
            if self.street2:
                street_line = f"{street_line} {self.street2.strip()}"
            return f"{street_line}, {self.city.strip()}, {self.state_code.strip()} {self.zip_code.strip()}"
        return ", ".join(pieces)

    # Priority classification
    priority_bucket: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    priority_bucket_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Realie.ai enrichment
    realie_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    realie_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    realie_match_confidence: Mapped[object | None] = mapped_column(
        Numeric(4, 3), nullable=True  # 1.0 = matched, 0.0 = 404/no match
    )
    realie_raw_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True  # complete Realie property response (all 80+ fields)
    )

    # Compatibility aliases used by the current API/tests.
    listing_url = synonym("source_url")
    address = synonym("street")
    unit_count = synonym("units")
    asking_cap_rate_pct = synonym("cap_rate")
    building_sqft = synonym("gba_sqft")
    seen_at = synonym("first_seen_at")
    scraped_at = synonym("last_seen_at")
