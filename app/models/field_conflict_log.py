"""Field-level disagreement log written during manual dedup merges.

When a user merges two ScrapedListing records via POST /dedup/{id}/merge,
the enhanced merge pass iterates an allowlist of fields:
  - canonical NULL, loser has value → copy value into canonical, log action='fill'
  - both non-null but disagree (beyond tolerance) → log action='conflict'
  - values agree → no log row

Logging both cases gives us a queryable record of cross-source disagreement
patterns, which drives source-priority tuning over time.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FieldConflictAction(str, enum.Enum):
    fill = "fill"
    conflict = "conflict"


class FieldConflictLog(Base):
    __tablename__ = "field_conflict_log"
    __table_args__ = (
        Index("ix_field_conflict_log_field_action", "field_name", "action"),
        Index("ix_field_conflict_log_sources", "canonical_source", "loser_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merge_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dedup_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )
    canonical_listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    loser_listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    loser_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_source: Mapped[str] = mapped_column(String(32), nullable=False)
    loser_source: Mapped[str] = mapped_column(String(32), nullable=False)
    # FieldConflictAction.fill or .conflict
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
