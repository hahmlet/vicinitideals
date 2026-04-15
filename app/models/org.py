"""Organization, User, ProjectVisibility models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import UniqueConstraint

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    deals: Mapped[list["Deal"]] = relationship(  # type: ignore[name-defined]
        "Deal", back_populates="organization"
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="organization"
    )
    portfolios: Mapped[list["Portfolio"]] = relationship(  # type: ignore[name-defined]
        "Portfolio", back_populates="organization"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Auth fields (added E2-P1B)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Email verification (soft gate — users can still log in when False,
    # they just see a "Please verify your email" banner on every page)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users"
    )
    project_visibilities: Mapped[list["ProjectVisibility"]] = relationship(
        "ProjectVisibility", back_populates="user"
    )


class ProjectVisibility(Base):
    __tablename__ = "project_visibilities"

    # project_id column references opportunities.id (table was renamed from projects)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        primary_key=True,
    )
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="project_visibilities")
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="project_visibilities"
    )
