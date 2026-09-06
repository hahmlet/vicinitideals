"""flats.word_rulings — what a word means here

The third inbox of the same shape, and the one that sits under the other two.
``crossref_rulings`` (0128) records a chapter we cannot open; ``reading_rulings``
(0129) a chapter we opened and decided about; this records what the *words*
those chapters are written in mean in this jurisdiction.

It exists because signing is not the first question. A number read correctly
out of its sentence is still wrong if the sentence measures it in a word the
city defines its own way — four codes in this corpus give four incompatible
tests for "corner lot", and seven subtract seven different lists from a "net
acre". Sign three hundred numbers before asking, and some of that signing has
to be done again.

Keyed by ``(layer, term)`` with the term in our vocabulary rather than the
city's: one code files "Lot, Width" and another writes "lot width", and keying
on their spelling would make the ledger uncountable.

Revision ID: 0130
Revises: 0129
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "word_rulings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("layer", sa.String(length=120), nullable=False),
        sa.Column("term", sa.String(length=60), nullable=False),
        sa.Column("standing", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=32), nullable=False),
        sa.Column("lots", sa.Integer(), nullable=True),
        sa.Column("values_touched", sa.Integer(), nullable=True),
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
        "ix_flats_word_rulings_pending",
        "word_rulings",
        ["decided_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("exported_at IS NULL"),
    )
    op.create_index(
        "ix_flats_word_rulings_card",
        "word_rulings",
        ["layer", "term", "decided_at"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_word_rulings_fingerprint",
        "word_rulings",
        ["fingerprint"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    for name in (
        "ix_flats_word_rulings_fingerprint",
        "ix_flats_word_rulings_card",
        "ix_flats_word_rulings_pending",
    ):
        op.drop_index(name, table_name="word_rulings", schema=SCHEMA)
    op.drop_table("word_rulings", schema=SCHEMA)
