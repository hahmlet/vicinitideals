"""Brokerage and broker ORM models for scraped listings."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
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

    @property
    def brokerage_name(self) -> str | None:
        return self.brokerage.name if self.brokerage is not None else None

    brokerage: Mapped["Brokerage | None"] = relationship("Brokerage", back_populates="brokers")
    scraped_listings: Mapped[list["ScrapedListing"]] = relationship(  # type: ignore[name-defined]
        "ScrapedListing",
        back_populates="broker",
    )
