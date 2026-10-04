"""flats.flag_reports: the nightly flag check and the design sensitivity report

Steph's flag plan (FOLLOWUPS 37 item 5): a nightly check that recomputes
every lot's colour and fails on a stored-vs-computed mismatch or an
incomplete flag, and a design sensitivity report -- what a pod a foot wider
or narrower does to the colours. Both read every row of the run in use, too
slow for a page load, so the nightly task writes one row here and the pages
read the newest.

Revision ID: 0142
Revises: 0141
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "flag_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("made_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_flag_reports_made_at", "flag_reports", ["made_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_flats_flag_reports_made_at", table_name="flag_reports", schema=SCHEMA)
    op.drop_table("flag_reports", schema=SCHEMA)
