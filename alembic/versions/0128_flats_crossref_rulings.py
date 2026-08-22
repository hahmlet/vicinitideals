"""flats.crossref_rulings — the fetch-triage inbox

Fetch triage records a decision about a chapter the store cannot open. Rules
themselves live in the repository, and the container rebuilds them from git on
every deploy, so a decision made in a browser needs somewhere durable to sit
until the drain writes it into the rule files for commit.

Same shape and same reasoning as ``flats.rule_signatures`` (0126): an inbox
with an ``exported_at`` stamp, so an undrained decision is visibly pending
rather than silently lost.

Revision ID: 0128
Revises: 0127
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "crossref_rulings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("layer", sa.String(length=120), nullable=False),
        sa.Column("ref", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("lots", sa.Integer(), nullable=True),
        sa.Column(
            "fields_touched", sa.Text(), server_default="", nullable=False
        ),
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
        "ix_flats_crossref_rulings_pending",
        "crossref_rulings",
        ["decided_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("exported_at IS NULL"),
    )
    op.create_index(
        "ix_flats_crossref_rulings_ref",
        "crossref_rulings",
        ["layer", "ref", "decided_at"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flats_crossref_rulings_ref", table_name="crossref_rulings", schema=SCHEMA
    )
    op.drop_index(
        "ix_flats_crossref_rulings_pending",
        table_name="crossref_rulings",
        schema=SCHEMA,
    )
    op.drop_table("crossref_rulings", schema=SCHEMA)
