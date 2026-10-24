"""flats.text_corrections: readers' notes of wrong words in the readable code text

One row per note: the words as the code library shows them and as the code
prints them, fixed later in batches (``fixed_at``).

Revision ID: 0146
Revises: 0145
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "text_corrections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document", sa.String(500), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("shown", sa.Text(), nullable=False),
        sa.Column("printed", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewer", sa.String(80), nullable=False),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("fixed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_text_corrections_document",
        "text_corrections",
        ["document", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_text_corrections_open",
        "text_corrections",
        ["created_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("fixed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_flats_text_corrections_open", table_name="text_corrections", schema=SCHEMA)
    op.drop_index("ix_flats_text_corrections_document", table_name="text_corrections", schema=SCHEMA)
    op.drop_table("text_corrections", schema=SCHEMA)
