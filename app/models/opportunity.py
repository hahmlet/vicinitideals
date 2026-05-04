"""Opportunity ORM — the unified investment target entity.

Renamed from ScrapedListing / scraped_listings table. Scraped rows and
manually-created rows share this table, distinguished by `source`.

Physical attributes (unit_count, building_sqft, year_built, etc.) already
populated by scrapers. NULL = read from parcel.*; non-null = permanent user
override. Parcel is the authoritative seed; these columns govern once set.

Override pattern:
    display_sqft     = opportunity.building_sqft  ?? parcel.building_sqft
    display_units    = opportunity.unit_count      ?? parcel.unit_count
    display_year     = opportunity.year_built      ?? parcel.year_built
"""

from __future__ import annotations

import builtins
import enum
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


class OpportunityStatus(str, enum.Enum):
    hypothetical = "hypothetical"
    active = "active"
    archived = "archived"


class OpportunityCategory(str, enum.Enum):
    proposed = "proposed"
    historical = "historical"


class OpportunitySource(str, enum.Enum):
    loopnet = "loopnet"
    crexi = "crexi"
    user_generated = "user_generated"
    manual = "manual"


# Backward-compat aliases
ProjectStatus = OpportunityStatus
ProjectCategory = OpportunityCategory
ProjectSource = OpportunitySource


class Opportunity(Base):
    """Unified investment target — scraped listing promoted to opportunity, or
    manually created. Physical attributes from scrapers; Parcel fills gaps.
    """

    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_scraped_listings_source_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ingest_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id"), nullable=True
    )

    # ── Source identity ───────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default=lambda: uuid.uuid4().hex
    )
    source_url: Mapped[str] = mapped_column("listing_url", Text, nullable=False)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Location ──────────────────────────────────────────────────────────
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

    # ── Physical attributes (Parcel-override) ─────────────────────────────
    # NULL = defer to parcel.*; non-null = permanent user override.
    property_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sub_type: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=True,
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
    apn_normalized: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=True,
    )
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

    # ── Listing metadata ──────────────────────────────────────────────────
    listing_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_description: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column("seen_at", DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        "scraped_at", DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matches_saved_criteria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # ── Foreign keys ──────────────────────────────────────────────────────
    broker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokers.id"), nullable=True
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=True
    )

    # ── Opportunity metadata (set at/after promotion) ─────────────────────
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    opp_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="hypothetical"
    )
    project_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="proposed"
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promotion_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    promotion_ruleset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_search_criteria.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Enrichment / scraper metadata ─────────────────────────────────────
    priority_bucket: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    priority_bucket_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    match_strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    match_confidence: Mapped[object | None] = mapped_column(Numeric(4, 3), nullable=True)
    lot_size_mismatch: Mapped[bool | None] = mapped_column(nullable=True, default=False)
    polygon_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=True,
    )
    apartment_style: Mapped[str | None] = mapped_column(String(40), nullable=True)
    construction_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parking_ratio: Mapped[str | None] = mapped_column(String(60), nullable=True)
    building_far: Mapped[object | None] = mapped_column(Numeric(8, 4), nullable=True)
    gross_rent_multiplier: Mapped[object | None] = mapped_column(Numeric(8, 4), nullable=True)
    on_ground_lease: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    highlights: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text).with_variant(JSON(), "sqlite"), nullable=True,
    )
    attachments: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    nearby_transportation: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    # Realie.ai enrichment
    realie_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    realie_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    realie_match_confidence: Mapped[object | None] = mapped_column(Numeric(4, 3), nullable=True)
    realie_raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # HelloData.ai enrichment
    hellodata_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hellodata_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hellodata_property_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hellodata_raw_search: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hellodata_raw_rents: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hellodata_raw_expenses: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hellodata_raw_comparables: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hellodata_market_rent_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hellodata_market_rent_per_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hellodata_egi_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hellodata_noi_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hellodata_opex_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    hellodata_occupancy_pct: Mapped[object | None] = mapped_column(Numeric(5, 4), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────
    ingest_job: Mapped["IngestJob | None"] = relationship(  # type: ignore[name-defined]
        "IngestJob", back_populates="scraped_listings",
    )
    broker: Mapped["Broker | None"] = relationship(  # type: ignore[name-defined]
        "Broker", back_populates="scraped_listings", foreign_keys=[broker_id],
    )
    parcel: Mapped["Parcel | None"] = relationship(  # type: ignore[name-defined]
        "Parcel", foreign_keys=[parcel_id],
    )
    organization: Mapped["Organization | None"] = relationship(  # type: ignore[name-defined]
        "Organization", foreign_keys=[org_id],
    )
    promotion_ruleset: Mapped["SavedSearchCriteria | None"] = relationship(  # type: ignore[name-defined]
        "SavedSearchCriteria", foreign_keys=[promotion_ruleset_id],
    )
    created_by_user: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_user_id],
    )
    # Projects that were created from this opportunity
    dev_projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="opportunity",
    )
    milestones: Mapped[list["Milestone"]] = relationship(  # type: ignore[name-defined]
        "Milestone",
        primaryjoin="and_(Milestone.opportunity_id == Opportunity.id, "
                    "Milestone.opportunity_id != None)",
        back_populates="opportunity",
    )
    permit_stubs: Mapped[list["PermitStub"]] = relationship(  # type: ignore[name-defined]
        "PermitStub", back_populates="opportunity",
    )
    parcel_transformations: Mapped[list["ParcelTransformation"]] = relationship(  # type: ignore[name-defined]
        "ParcelTransformation", back_populates="opportunity",
    )
    project_visibilities: Mapped[list["ProjectVisibility"]] = relationship(  # type: ignore[name-defined]
        "ProjectVisibility", back_populates="opportunity",
    )
    sensitivities: Mapped[list["Sensitivity"]] = relationship(  # type: ignore[name-defined]
        "Sensitivity", back_populates="opportunity",
    )
    portfolio_projects: Mapped[list["PortfolioProject"]] = relationship(  # type: ignore[name-defined]
        "PortfolioProject", back_populates="opportunity",
    )
    gantt_entries: Mapped[list["GanttEntry"]] = relationship(  # type: ignore[name-defined]
        "GanttEntry", back_populates="opportunity",
    )

    # ── Computed helpers ──────────────────────────────────────────────────

    @builtins.property
    def full_address(self) -> str | None:
        parts = [self.street, self.street2, self.city, self.state_code, self.zip_code]
        pieces = [str(p).strip() for p in parts if p not in (None, "") and str(p).strip()]
        if not pieces:
            return None
        if self.street and self.city and self.state_code and self.zip_code:
            street_line = self.street.strip()
            if self.street2:
                street_line = f"{street_line} {self.street2.strip()}"
            return f"{street_line}, {self.city.strip()}, {self.state_code.strip()} {self.zip_code.strip()}"
        return ", ".join(pieces)

    @builtins.property
    def display_name(self) -> str:
        """User-set name override; falls back to address or listing_name."""
        return self.name or self.listing_name or self.address_normalized or self.address_raw or str(self.id)

    def effective_unit_count(self, parcel: "Parcel | None" = None) -> int | None:  # type: ignore[name-defined]
        """unit_count with Parcel fallback. Pass parcel to avoid extra query."""
        if self.units is not None:
            return self.units
        return getattr(parcel, "unit_count", None) if parcel else (
            self.parcel.unit_count if self.parcel else None
        )

    def effective_building_sqft(self, parcel: "Parcel | None" = None) -> object | None:
        """building_sqft with Parcel fallback."""
        if self.gba_sqft is not None:
            return self.gba_sqft
        return getattr(parcel, "building_sqft", None) if parcel else (
            self.parcel.building_sqft if self.parcel else None
        )

    # ── Compatibility synonyms (keep existing code working) ───────────────
    listing_url = synonym("source_url")
    address = synonym("street")
    unit_count = synonym("units")
    asking_cap_rate_pct = synonym("cap_rate")
    building_sqft = synonym("gba_sqft")
    seen_at = synonym("first_seen_at")
    scraped_at = synonym("last_seen_at")
