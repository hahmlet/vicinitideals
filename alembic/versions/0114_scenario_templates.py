"""Add scenario_templates table and default_template_id on org/user.

Revision ID: 0114
Revises: 0113
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_scenario_id", UUID(as_uuid=True), sa.ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_type", sa.String(50), nullable=True),
        sa.Column("template_json", JSONB(), nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_scenario_templates_org_id", "scenario_templates", ["org_id"])

    # Nullable UUID columns for org/user defaults — no FK to avoid circular dep
    op.add_column("organizations", sa.Column("default_template_id", UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("default_template_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "default_template_id")
    op.drop_column("organizations", "default_template_id")
    op.drop_index("ix_scenario_templates_org_id", "scenario_templates")
    op.drop_table("scenario_templates")
