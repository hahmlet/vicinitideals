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
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
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
