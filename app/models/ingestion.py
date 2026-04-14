"""IngestJob, DedupCandidate, SavedSearchCriteria models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class RecordType(str, enum.Enum):
    listing = "listing"
    permit = "permit"
    parcel = "parcel"


class DedupStatus(str, enum.Enum):
    pending = "pending"
    merged = "merged"
    kept_separate = "kept_separate"
    swapped = "swapped"


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_duplicate_exact: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_flagged_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    dedup_candidates: Mapped[list["DedupCandidate"]] = relationship(
        "DedupCandidate", back_populates="ingest_job"
    )
    scraped_listings: Mapped[list["ScrapedListing"]] = relationship(  # type: ignore[name-defined]
        "ScrapedListing", back_populates="ingest_job"
    )


class DedupCandidate(Base):
    __tablename__ = "dedup_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ingest_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_jobs.id"), nullable=False
    )
    record_a_type: Mapped[RecordType] = mapped_column(String(30), nullable=False)
    record_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_b_type: Mapped[RecordType] = mapped_column(String(30), nullable=False)
    record_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[DedupStatus] = mapped_column(
        String(30), nullable=False, default=DedupStatus.pending
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    ingest_job: Mapped["IngestJob"] = relationship(
        "IngestJob", back_populates="dedup_candidates"
    )
    resolved_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User"
    )


class SavedSearchCriteria(Base):
    __tablename__ = "saved_search_criteria"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    min_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_price: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    zip_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    property_types: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    sources: Mapped[list[str] | None] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # When True (default), every listing that matches this criteria is automatically
    # promoted to an Opportunity at ingest time without requiring user review.
    auto_promote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
