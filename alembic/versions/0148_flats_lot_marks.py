"""flats.lot_marks: person-entered lot marks, retained when cleared

Revision ID: 0148
Revises: 0147
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_marks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "lot_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "cleared_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clear_note", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('trees')", name="ck_flats_lot_marks_kind"),
        sa.CheckConstraint("char_length(note) <= 2000", name="ck_flats_lot_marks_note_length"),
        sa.CheckConstraint(
            "clear_note IS NULL OR char_length(clear_note) <= 2000",
            name="ck_flats_lot_marks_clear_note_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_flats_lot_marks_open",
        "lot_marks",
        ["lot_id", "kind"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("cleared_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_flats_lot_marks_open", table_name="lot_marks", schema=SCHEMA)
    op.drop_table("lot_marks", schema=SCHEMA)
