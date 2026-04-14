"""Workflow run manifest persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vicinitideals.models.base import Base


class WorkflowRunManifest(Base):
    __tablename__ = "workflow_run_manifests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scenarios.id"),
        nullable=False,
        index=True,
    )
    engine: Mapped[str] = mapped_column(String(50), nullable=False)
    inputs_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    outputs_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scenario: Mapped["Scenario"] = relationship(  # type: ignore[name-defined]
        "Scenario", back_populates="workflow_run_manifests"
    )
