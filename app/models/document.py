"""Document model — files in a Project's document room.

A Document is one uploaded file scoped to a Project (a sub-component of a Deal,
tracked separately). ``org_id`` is denormalized from the Project's
Scenario→Deal so document queries can be org-scoped and isolated the same way
the rest of the app is (see ``_apply_org_scope``). File *bytes* live on disk
under the doc-room storage root (``app/storage/documents.py``); this row holds
only metadata plus the storage key that points at the bytes.

Phase 1 of the document-room module. ``preview_status`` / ``preview_key`` back
the Phase 1b server-side Office→PDF conversion (PDFs/images render natively and
need no preview).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class DocumentPreviewStatus(str, enum.Enum):
    none = "none"        # native render (PDF/image) or preview not requested
    pending = "pending"  # Office→PDF conversion queued / in flight
    ready = "ready"      # preview_key points at a converted PDF
    failed = "failed"    # conversion failed; download still works


class Document(Base):
    """One uploaded file in a Project's document room."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_project_status", "org_id", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Optional "subfolder" — the task this file belongs to. Null = project root.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Relative path under settings.document_storage_path (bytes on disk).
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        String(20), nullable=False, default=DocumentStatus.active, server_default="active"
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    preview_status: Mapped[DocumentPreviewStatus] = mapped_column(
        String(20), nullable=False, default=DocumentPreviewStatus.none, server_default="none"
    )
    preview_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentTaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"


class DocumentTask(Base):
    """A document-collection task ("subfolder") within a Project's room.

    Tracking-only: status/due are for keeping the user oriented. There is NO
    gating — completion never triggers or blocks anything (mirrors, does not
    extend, ``Project.timeline_approved``). Due date is either hard-coded
    (``due_date``) or resolved relative to a Milestone (``due_milestone_id`` +
    ``due_offset_days``) via :meth:`computed_due_date`.
    """

    __tablename__ = "document_tasks"
    __table_args__ = (
        Index("ix_document_tasks_project", "org_id", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[DocumentTaskStatus] = mapped_column(
        String(20), nullable=False, default=DocumentTaskStatus.pending, server_default="pending"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hard-coded due date (used when due_milestone_id is null).
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Relational due date: resolves to milestone end + offset_days.
    due_milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("milestones.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_offset_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def computed_due_date(
        self, milestone_map: "dict[uuid.UUID, object] | None" = None
    ) -> date | None:
        """Resolve the effective due date.

        Relative (milestone) due dates win when set: milestone end + offset.
        ``milestone_map`` maps milestone id → Milestone (for trigger-chain
        resolution via ``computed_end``). Falls back to ``due_date``.
        """
        if self.due_milestone_id is not None and milestone_map is not None:
            milestone = milestone_map.get(self.due_milestone_id)
            if milestone is not None:
                end = milestone.computed_end(milestone_map)
                if end is not None:
                    return end + timedelta(days=self.due_offset_days or 0)
        return self.due_date


class DocumentShare(Base):
    """A revocable external share link for a Project's document room.

    The link carries a signed token (``itsdangerous``) whose payload is this
    row's id. Validity is DB-backed: a share can be revoked instantly
    (``revoked=True``) regardless of the token's signature/expiry. Guests
    reaching the room via a valid, non-revoked share may view tasks/documents,
    upload, and download — but NOT archive or delete (no destructive routes
    are exposed under the guest prefix). No passcode gate.
    """

    __tablename__ = "document_shares"
    __table_args__ = (
        Index("ix_document_shares_project", "org_id", "project_id"),
        Index("ix_document_shares_slug", "slug", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Short, URL-friendly random code (base58 — no 0/O/I/l). Guests reach the
    # room via /share/{slug}. Unguessable; validity is still DB-backed (revoked
    # flag + created_at age check), not embedded in the code.
    slug: Mapped[str] = mapped_column(String(32), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Optional human label, e.g. "Sent to lender".
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentTaskTemplate(Base):
    """An org-level default task seeded onto every newly-created Project.

    Name-only: when a Project is created, one ``DocumentTask`` (status pending,
    no due date) is created per template. Templates do NOT backfill existing
    projects — they apply to future projects only.
    """

    __tablename__ = "document_task_templates"
    __table_args__ = (
        Index("ix_document_task_templates_org", "org_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DealShare(Base):
    """A revocable guest link to a whole Deal's document rooms.

    Unlike ``DocumentShare`` (one Project), a DealShare grants a guest access to
    every Project under the Deal: the landing page lists the projects and the
    guest picks one to work in. Validity is DB-backed (``revoked`` flag +
    ``created_at`` age check); ``slug`` is the same short base58 code style.
    """

    __tablename__ = "deal_shares"
    __table_args__ = (
        Index("ix_deal_shares_deal", "org_id", "deal_id"),
        Index("ix_deal_shares_slug", "slug", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(32), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
