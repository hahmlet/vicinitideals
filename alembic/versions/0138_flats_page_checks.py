"""flats.page_checks: numbers checked against the printed page

Signing compares an encoded number with our text copy of the code. This table
holds the answers to the same question asked of the printed page -- the card
shows the city's own sheet with a box on the cell we read, and asks whether it
says what we encoded, then one question per footnote printed on it.

Revision ID: 0138
Revises: 0137
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "page_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("layer", sa.String(120), nullable=False),
        sa.Column("zone", sa.String(40), nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("when_key", sa.String(200), nullable=False, server_default=""),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("question", sa.String(40), nullable=False),
        sa.Column("answer", sa.String(16), nullable=False),
        sa.Column("says", sa.Text(), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("quote", sa.Text(), nullable=False, server_default=""),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("placed", sa.String(16), nullable=False, server_default=""),
        sa.Column("book_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("reviewer", sa.String(80), nullable=False),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("bundled_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_page_checks_value",
        "page_checks",
        ["layer", "zone", "field", "when_key"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_page_checks_fingerprint", "page_checks", ["fingerprint"], schema=SCHEMA
    )
    op.create_index(
        "ix_flats_page_checks_unbundled",
        "page_checks",
        ["decided_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("bundled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_flats_page_checks_unbundled", table_name="page_checks", schema=SCHEMA)
    op.drop_index("ix_flats_page_checks_fingerprint", table_name="page_checks", schema=SCHEMA)
    op.drop_index("ix_flats_page_checks_value", table_name="page_checks", schema=SCHEMA)
    op.drop_table("page_checks", schema=SCHEMA)
