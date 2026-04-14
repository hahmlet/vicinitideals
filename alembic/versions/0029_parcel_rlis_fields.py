"""Add Metro RLIS taxlot fields to parcels table.

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("sale_price", sa.Integer(), nullable=True))
    op.add_column("parcels", sa.Column("sale_date", sa.String(6), nullable=True))  # RLIS YYYYMM format
    op.add_column("parcels", sa.Column("state_class", sa.String(10), nullable=True))  # STATECLASS
    op.add_column("parcels", sa.Column("ortaxlot", sa.String(50), nullable=True))  # ORTAXLOT (alternate format)
    op.add_column("parcels", sa.Column("primary_account_num", sa.String(20), nullable=True))  # PRIMACCNUM
    op.add_column("parcels", sa.Column("alt_account_num", sa.String(20), nullable=True))  # ALTACCNUM
    op.add_column("parcels", sa.Column("rlis_land_use", sa.String(10), nullable=True))  # LANDUSE 3-char code
    op.add_column("parcels", sa.Column("rlis_taxcode", sa.String(20), nullable=True))  # TAXCODE (RLIS, may differ from county)
    op.create_index("ix_parcels_ortaxlot", "parcels", ["ortaxlot"], unique=False)
    op.create_index("ix_parcels_state_class", "parcels", ["state_class"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_parcels_state_class", table_name="parcels")
    op.drop_index("ix_parcels_ortaxlot", table_name="parcels")
    op.drop_column("parcels", "rlis_taxcode")
    op.drop_column("parcels", "rlis_land_use")
    op.drop_column("parcels", "alt_account_num")
    op.drop_column("parcels", "primary_account_num")
    op.drop_column("parcels", "ortaxlot")
    op.drop_column("parcels", "state_class")
    op.drop_column("parcels", "sale_date")
    op.drop_column("parcels", "sale_price")
