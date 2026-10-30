"""flats.lot_works_as: per run, lot and design, is the pod green as an apartment / as townhomes

Worked out once at load so the Lots page's "Works as" filter does not group
the whole run's results JSON on every request (FOLLOWUPS 121).

Revision ID: 0147
Revises: 0146
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_works_as",
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("design_key", sa.String(80), primary_key=True),
        sa.Column("apartment_green", sa.Boolean(), nullable=True),
        sa.Column("townhomes_green", sa.Boolean(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_works_as_run_design", "lot_works_as", ["run_id", "design_key"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_flats_lot_works_as_run_design", table_name="lot_works_as", schema=SCHEMA)
    op.drop_table("lot_works_as", schema=SCHEMA)
