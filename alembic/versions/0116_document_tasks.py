"""Add document_tasks table + documents.task_id (Phase 2 — task view).

Revision ID: 0116
Revises: 0115
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_milestone_id", UUID(as_uuid=True), sa.ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "ix_document_tasks_project", "document_tasks", ["org_id", "project_id", "status"]
    )
    op.add_column(
        "documents",
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("document_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "task_id")
    op.drop_index("ix_document_tasks_project", "document_tasks")
    op.drop_table("document_tasks")
