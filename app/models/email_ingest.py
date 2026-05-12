"""InboundEmail and EmailDealSuggestion ORM models for email-to-deal pipeline."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class InboundEmailStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    deal_created = "deal_created"
    failed = "failed"
    spam = "spam"


class SuggestionSourceType(str, enum.Enum):
    email_body = "email_body"
    proforma_xlsx = "proforma_xlsx"
    llm_extraction = "llm_extraction"


class InboundEmail(Base):
    """An email received at deals@viciniti.deals awaiting deal creation."""

    __tablename__ = "inbound_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sender_email: Mapped[str] = mapped_column(Text(), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(Text(), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text(), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    raw_mime_b64: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=InboundEmailStatus.pending.value
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="SET NULL"),
        nullable=True,
    )
    proforma_task_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    debug_log: Mapped[str | None] = mapped_column(Text(), nullable=True)
    attachments_meta: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization"
    )
    deal: Mapped["Deal | None"] = relationship(  # type: ignore[name-defined]
        "Deal", foreign_keys=[deal_id]
    )
    suggestions: Mapped[list["EmailDealSuggestion"]] = relationship(
        "EmailDealSuggestion",
        back_populates="inbound_email",
        cascade="all, delete-orphan",
    )


class EmailDealSuggestion(Base):
    """A field-level suggestion extracted from an inbound email or its attachments."""

    __tablename__ = "email_deal_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inbound_email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inbound_emails.id", ondelete="CASCADE"),
        nullable=False,
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_path: Mapped[str] = mapped_column(Text(), nullable=False)
    suggested_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float(), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    accepted: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)

    # Relationships
    inbound_email: Mapped["InboundEmail"] = relationship(
        "InboundEmail", back_populates="suggestions"
    )
