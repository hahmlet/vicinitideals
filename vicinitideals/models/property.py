"""Building model — curated property promoted from raw scraped listings (was 'Property').

Buildings live inside Opportunities. One Opportunity may reference multiple Buildings
(e.g., a portfolio sale of 10 buildings). A Building may appear in multiple Opportunities
(e.g., two separate deal attempts on the same property) via OpportunityBuilding join table.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vicinitideals.models.base import Base


class BuildingStatus(str, enum.Enum):
    existing = "existing"       # building still standing
    archived = "archived"       # demolished / no longer relevant


class Building(Base):
    """A physical structure at an address (was 'Property', table: buildings)."""

    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Address ───────────────────────────────────────────────────────────────
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # ── Physical attributes ───────────────────────────────────────────────────
    unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_sqft: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    net_rentable_sqft: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # e.g. "Multifamily", "Mixed Use", "Commercial", "Single Family"
    property_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # e.g. "Residential Income", "Vacant Land", "Office"
    current_use: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Financial / listing ───────────────────────────────────────────────────
    asking_price: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    asking_cap_rate_pct: Mapped[object | None] = mapped_column(Numeric(8, 4), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[BuildingStatus] = mapped_column(
        String(20), nullable=False, default=BuildingStatus.existing
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Source linkages ───────────────────────────────────────────────────────
    scraped_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scraped_listings.id"), nullable=True, unique=True
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parcels.id"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    scraped_listing: Mapped["ScrapedListing | None"] = relationship(  # type: ignore[name-defined]
        "ScrapedListing",
        foreign_keys=[scraped_listing_id],
    )
    parcel: Mapped["Parcel | None"] = relationship("Parcel")  # type: ignore[name-defined]
    created_by_user: Mapped["User | None"] = relationship("User")  # type: ignore[name-defined]
    opportunity_buildings: Mapped[list["OpportunityBuilding"]] = relationship(
        "OpportunityBuilding", back_populates="building"
    )

    @property
    def address_display(self) -> str:
        parts = [self.address_line1, self.city]
        if self.state:
            parts.append(self.state)
        if self.zip_code:
            parts.append(self.zip_code)
        return ", ".join(p for p in parts if p) or self.name


class OpportunityBuilding(Base):
    """Join table: one Opportunity → many Buildings (and a Building can appear in many Opportunities)."""

    __tablename__ = "opportunity_buildings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    # Display order within the opportunity
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional: role of this building in the opportunity
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "primary", "adjacent"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="opportunity_buildings"
    )
    building: Mapped["Building"] = relationship(
        "Building", back_populates="opportunity_buildings"
    )


# Backward-compat alias
Property = Building
