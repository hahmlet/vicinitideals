"""Brokerage and broker ORM models for scraped listings."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Brokerage(Base):
    __tablename__ = "brokerages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    crexi_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    street: Mapped[str | None] = mapped_column(Text, nullable=True)
    street2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Oregon eLicense "Affiliated with" enrichment — the firm address from the
    # Oregon record, kept separate from the listing-derived street/city so we
    # don't clobber listing data with the Oregon view.
    oregon_company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    oregon_company_street: Mapped[str | None] = mapped_column(Text, nullable=True)
    oregon_company_street2: Mapped[str | None] = mapped_column(Text, nullable=True)
    oregon_company_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    oregon_company_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    oregon_company_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Firm-scraper registry state. Drives the firm-name color in UI:
    # 'supported' → green, 'unsupported' → red, 'unknown' → grey.
    firm_scrape_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="unknown"
    )
    firm_scrape_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    brokers: Mapped[list["Broker"]] = relationship("Broker", back_populates="brokerage")


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    crexi_broker_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    crexi_global_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_platinum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    number_of_assets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brokerage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brokerages.id"), nullable=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_state: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # When True, listing scrapers must NOT overwrite license_number — the user
    # has manually aligned it to the Oregon database. Oregon enrichment still
    # runs against whatever license_number is set.
    license_number_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    # Personal/home address from the Oregon license record.
    license_personal_street: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_personal_street2: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_personal_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_personal_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    license_personal_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)

    license_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 'active' | 'inactive' | 'not_found' | 'unknown'
    license_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    oregon_last_pulled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'success' | 'failed' | 'not_found' | 'pending'
    oregon_lookup_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    oregon_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    oregon_detail_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def brokerage_name(self) -> str | None:
        return self.brokerage.name if self.brokerage is not None else None

    brokerage: Mapped["Brokerage | None"] = relationship("Brokerage", back_populates="brokers")
    scraped_listings: Mapped[list["ScrapedListing"]] = relationship(  # type: ignore[name-defined]
        "ScrapedListing",
        back_populates="broker",
    )
    disciplinary_actions: Mapped[list["BrokerDisciplinaryAction"]] = relationship(
        "BrokerDisciplinaryAction",
        back_populates="broker",
        cascade="all, delete-orphan",
        order_by="BrokerDisciplinaryAction.order_signed_date.desc()",
    )


class BrokerDisciplinaryAction(Base):
    """One row per disciplinary case found on a broker's Oregon record."""

    __tablename__ = "broker_disciplinary_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brokers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    order_signed_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    found_issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pulled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    broker: Mapped["Broker"] = relationship("Broker", back_populates="disciplinary_actions")
