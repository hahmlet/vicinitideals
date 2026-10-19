"""flats.document_readthroughs: completed human reads of printed documents

Each completed read-through is one immutable row, with the reviewer's notes
and optional marked regions stored together as a JSON list.

Revision ID: 0144
Revises: 0143
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "document_readthroughs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document", sa.String(500), nullable=False),
        sa.Column("book_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column(
            "comments", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviewer", sa.String(80), nullable=False),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_document_readthroughs_document_submitted",
        "document_readthroughs",
        ["document", "submitted_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flats_document_readthroughs_document_submitted",
        table_name="document_readthroughs",
        schema=SCHEMA,
    )
    op.drop_table("document_readthroughs", schema=SCHEMA)
