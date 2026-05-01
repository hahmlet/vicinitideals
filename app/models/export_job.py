"""Async investor-export job persistence.

Tracks one row per Excel-export request so the UI can show progress (hover
modal: Calculating → Sending Email → Send Confirmed) and resend a cached
build when the underlying scenario hasn't been recomputed since the last
successful export.

Lifecycle::

    queued → calculating → sending → sent
                              └────→ failed (terminal, with error message)

``xlsx_bytes`` carries the rendered workbook so a "resend last export"
click can ship the same file without re-running the engine.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExportJobStatus(str, enum.Enum):
    queued = "queued"
    calculating = "calculating"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[ExportJobStatus] = mapped_column(
        SqlEnum(ExportJobStatus, name="export_job_status"),
        nullable=False,
        default=ExportJobStatus.queued,
    )
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    xlsx_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
