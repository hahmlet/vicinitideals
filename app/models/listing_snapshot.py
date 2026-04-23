"""Point-in-time snapshots of LoopNet SaleDetails / ExtendedDetails responses.

Populated by the 30-day seed experiment (app/tasks/loopnet_ingest.py
loopnet_experiment_daily_refresh) to characterize how frequently listings are
updated by brokers. Each row captures the raw JSON payload at a given moment;
post-experiment analysis diffs consecutive rows to produce per-field change
histograms.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    __table_args__ = (
        Index("ix_listing_snapshots_listing_captured", "listing_id", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 'sale_details' | 'extended_details'
    endpoint: Mapped[str] = mapped_column(String(32), nullable=False)
    # Full response body. JSONB in Postgres, JSON in SQLite for tests.
    raw_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    # Parsed `lastUpdated` from the response — used to cheaply detect changes
    # between snapshots without diffing the full payload.
    source_last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
