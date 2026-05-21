"""OrgSetting and UserSetting ORM models — org & user defaults system.

OrgSetting: per-org field defaults, set by org admin.
  - All keys in ORG_SET_FIELDS (app/settings/defaults.py) are Type 1 Org-Set:
    users cannot override in-model; these inputs render with readonly.
  - All other keys are Type 2 Org-Default: user may override with UserSetting.

UserSetting: per-user, per-org field overrides (Type 3 User-Default).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrgSetting(Base):
    __tablename__ = "org_settings"
    __table_args__ = (UniqueConstraint("org_id", "field_key", name="uq_org_settings_org_field"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Stored as text; callers cast to the appropriate Python type at read time.
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # When False, UserSetting rows for this field are ignored by the resolver.
    user_overridable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Phase 5 (deferred): "range" | "list" | None
    constraint_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraint_min: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    constraint_max: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    constraint_options: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "field_key", name="uq_user_settings_user_field"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrgDealTypeDefault(Base):
    __tablename__ = "org_deal_type_defaults"
    __table_args__ = (UniqueConstraint("org_id", "deal_type", "milestone_type", name="uq_org_deal_type_defaults"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    deal_type: Mapped[str] = mapped_column(Text, nullable=False)
    milestone_type: Mapped[str] = mapped_column(Text, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    duration_days: Mapped[int | None] = mapped_column(Numeric, nullable=True)
    starts_after_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    offset_days: Mapped[int] = mapped_column(Numeric, nullable=False, default=0, server_default="0")
    user_overridable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


class UserDealTypeDefault(Base):
    __tablename__ = "user_deal_type_defaults"
    __table_args__ = (UniqueConstraint("user_id", "deal_type", "milestone_type", name="uq_user_deal_type_defaults"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deal_type: Mapped[str] = mapped_column(Text, nullable=False)
    milestone_type: Mapped[str] = mapped_column(Text, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    duration_days: Mapped[int | None] = mapped_column(Numeric, nullable=True)
    starts_after_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    offset_days: Mapped[int] = mapped_column(Numeric, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
