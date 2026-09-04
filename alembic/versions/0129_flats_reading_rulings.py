"""flats.reading_rulings — the reading-queue inbox

The reading queues regroup the uncited ledger into section cards and ask one of
four questions about each. This is where the answers land.

Same shape and same reasoning as ``flats.crossref_rulings`` (0128): rules live
in the repository, the container rebuilds them from git on every deploy, and a
decision made in a browser needs somewhere durable to sit until the drain
writes it into the rule files for commit.

One column the crossref inbox does not have: ``fingerprint``, the section as it
read when the decision was made. A queue that outlives its reasons spends a
reviewer's attention on questions that answered themselves, so a ruling whose
fingerprint no longer matches reopens rather than silently keeping a card shut
against text nobody has seen.

Revision ID: 0129
Revises: 0128
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "reading_rulings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("layer", sa.String(length=120), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("section", sa.String(length=60), server_default="", nullable=False),
        sa.Column("queue", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=32), nullable=False),
        sa.Column("lots", sa.Integer(), nullable=True),
        sa.Column("lines", sa.Integer(), nullable=True),
        sa.Column("fields_touched", sa.Text(), server_default="", nullable=False),
        sa.Column("decided_by", sa.String(length=200), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_reading_rulings_pending",
        "reading_rulings",
        ["decided_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("exported_at IS NULL"),
    )
    op.create_index(
        "ix_flats_reading_rulings_card",
        "reading_rulings",
        ["layer", "path", "section", "decided_at"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_reading_rulings_fingerprint",
        "reading_rulings",
        ["fingerprint"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    for name in (
        "ix_flats_reading_rulings_fingerprint",
        "ix_flats_reading_rulings_card",
        "ix_flats_reading_rulings_pending",
    ):
        op.drop_index(name, table_name="reading_rulings", schema=SCHEMA)
    op.drop_table("reading_rulings", schema=SCHEMA)
