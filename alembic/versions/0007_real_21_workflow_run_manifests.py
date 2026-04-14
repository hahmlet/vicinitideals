"""REAL-21 workflow run manifests

Revision ID: 0007
Revises: 0004
Create Date: 2026-04-03 18:45:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_run_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engine", sa.String(length=50), nullable=False),
        sa.Column("inputs_json", sa.JSON(), nullable=True),
        sa.Column("outputs_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_run_manifests_model_id"),
        "workflow_run_manifests",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_run_manifests_run_id"),
        "workflow_run_manifests",
        ["run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_run_manifests_run_id"), table_name="workflow_run_manifests")
    op.drop_index(op.f("ix_workflow_run_manifests_model_id"), table_name="workflow_run_manifests")
    op.drop_table("workflow_run_manifests")
