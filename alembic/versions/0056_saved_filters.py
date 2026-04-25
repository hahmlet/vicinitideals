"""saved_filters: per-user, per-page named filter snapshots.

Stores a name + URL query string per user/page so users can save and
share their filter set on Listings/Parcels/Opportunities/Deals. The
search box (?q=) is intentionally excluded from saved snapshots client-
side — saved filters describe a market slice, not a search.

Revision ID: 0056
Revises: 0055
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_filters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("query_string", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "page", "name", name="uq_saved_filters_user_page_name"),
    )
    op.create_index("ix_saved_filters_user_page", "saved_filters", ["user_id", "page"])


def downgrade() -> None:
    op.drop_index("ix_saved_filters_user_page", table_name="saved_filters")
    op.drop_table("saved_filters")
