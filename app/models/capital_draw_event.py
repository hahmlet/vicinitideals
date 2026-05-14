"""CapitalDrawEvent — audit trail of per-period capital draws from funding sources."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class DrawAllocationReason(str, enum.Enum):
    acquisition = "acquisition"
    period_funding = "period_funding"
    reserve_prefund = "reserve_prefund"
    refi_proceeds = "refi_proceeds"


class CapitalDrawEvent(Base):
    """One row per capital inflow event per period for a scenario/project.

    Written by compute_cash_flows on each run (prior rows purged first).
    Replaces the month-0 total_sources pre-seed: draw amounts sum to the
    same total but are distributed across periods when the capital actually
    flows in to fund uses.
    """

    __tablename__ = "capital_draw_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    period_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    allocation_reason: Mapped[str] = mapped_column(
        String(40), nullable=False, default=DrawAllocationReason.period_funding
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capital_modules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    use_line_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
