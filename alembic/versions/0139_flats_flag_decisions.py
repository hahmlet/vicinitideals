"""flats.flag_decisions: a person approving a flag type's numbers

Steph's flag plan: the risk, severity, resolution and priority of every kind
of unknown, and the rule set that turns them into a colour, are a person's to
set; an agent only proposes them. The approval page writes a row here, and
``scripts/flats_drain_flag_decisions.py`` writes it into flags.yaml /
colour.yaml for commit -- the screen reads the files, the inbox bargain of
0128 and 0129.

Revision ID: 0139
Revises: 0138
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "flag_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("values", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_by", sa.String(200), nullable=False),
        sa.Column(
            "decided_user_id",
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
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_flag_decisions_pending",
        "flag_decisions",
        ["decided_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("exported_at IS NULL"),
    )
    op.create_index(
        "ix_flats_flag_decisions_subject",
        "flag_decisions",
        ["subject", "decided_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_flats_flag_decisions_subject", table_name="flag_decisions", schema=SCHEMA)
    op.drop_index("ix_flats_flag_decisions_pending", table_name="flag_decisions", schema=SCHEMA)
    op.drop_table("flag_decisions", schema=SCHEMA)
