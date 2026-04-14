"""Realie.ai monthly API call budget tracking."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RealieUsage(Base):
    __tablename__ = "realie_usage"

    month: Mapped[str] = mapped_column(
        String(7), primary_key=True  # "2026-04"
    )
    calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    call_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_call_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def calls_remaining(self) -> int:
        return max(0, self.call_limit - self.calls_used)

    @property
    def is_locked(self) -> bool:
        return self.locked or self.calls_used >= self.call_limit
