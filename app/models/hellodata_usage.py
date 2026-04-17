"""HelloData.ai monthly API call budget tracking.

Tracks per-month call count and cost (in cents) against a configurable
monthly budget.  Each endpoint call is one row in the `calls_used`
counter regardless of endpoint — all four HelloData endpoints cost
the same per-call rate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HelloDataUsage(Base):
    __tablename__ = "hellodata_usage"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # "2026-04"
    calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
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
    def budget_remaining_cents(self) -> int:
        return max(0, self.budget_cents - self.cost_cents)

    @property
    def is_locked(self) -> bool:
        return self.locked or self.cost_cents >= self.budget_cents
