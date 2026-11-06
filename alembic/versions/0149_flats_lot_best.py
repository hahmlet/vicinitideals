"""flats.lot_best: per run and lot, the best verdict/colour across designs

The Lots page reads this instead of grouping all result rows on each request.
Rows also carry jurisdiction/zone/tlid/address so list filters and city/tlid
sorts avoid joining the wide flats.lots table.

Revision ID: 0149
Revises: 0148
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_best",
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("jurisdiction", sa.String(80), nullable=False),
        sa.Column("zone", sa.String(40), nullable=True),
        sa.Column("tlid", sa.String(40), nullable=False),
        sa.Column("site_address", sa.String(255), nullable=True),
        sa.Column("best_verdict", sa.Integer(), nullable=False),
        sa.Column("best_colour", sa.Integer(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_best_run_verdict_colour",
        "lot_best",
        ["run_id", "best_verdict", "best_colour"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_best_run_jurisdiction_zone",
        "lot_best",
        ["run_id", "jurisdiction", "zone"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_best_run_jurisdiction_tlid",
        "lot_best",
        ["run_id", "jurisdiction", "tlid", "lot_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_flats_lot_best_run_jurisdiction_tlid", table_name="lot_best", schema=SCHEMA)
    op.drop_index("ix_flats_lot_best_run_jurisdiction_zone", table_name="lot_best", schema=SCHEMA)
    op.drop_index("ix_flats_lot_best_run_verdict_colour", table_name="lot_best", schema=SCHEMA)
    op.drop_table("lot_best", schema=SCHEMA)
