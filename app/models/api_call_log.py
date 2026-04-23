"""Per-call log for external API usage (LoopNet, and extensible to other sources).

Used by app/scrapers/loopnet.py BudgetGuard to count calls per billing_month
and short-circuit the scraper before it exceeds the monthly tier limit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiCallLog(Base):
    __tablename__ = "api_call_log"
    __table_args__ = (
        Index("ix_api_call_log_month_source", "billing_month", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    listing_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Computed at insert time as date(called_at) truncated to first-of-month —
    # kept as a plain column (not computed) so SQLite/Alembic don't need stored-generated support.
    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
