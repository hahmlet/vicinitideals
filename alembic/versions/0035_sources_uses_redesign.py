"""Add offset days, funder_type, and capital_module_id to draw_sources.

Revision ID: 0035
Revises: 0034
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("draw_sources", sa.Column(
        "active_from_offset_days", sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column("draw_sources", sa.Column(
        "active_to_offset_days", sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column("draw_sources", sa.Column(
        "funder_type", sa.String(60), nullable=True
    ))
    op.add_column("draw_sources", sa.Column(
        "capital_module_id", UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        "fk_draw_sources_capital_module",
        "draw_sources", "capital_modules",
        ["capital_module_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_draw_sources_capital_module", "draw_sources", type_="foreignkey")
    op.drop_column("draw_sources", "capital_module_id")
    op.drop_column("draw_sources", "funder_type")
    op.drop_column("draw_sources", "active_to_offset_days")
    op.drop_column("draw_sources", "active_from_offset_days")
