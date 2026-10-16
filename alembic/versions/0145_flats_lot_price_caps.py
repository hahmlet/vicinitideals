"""Additional FLATS lot price caps and optional net area

Revision ID: 0145
Revises: 0144
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.add_column("lot_prices", sa.Column("cap_max_units", sa.Numeric(10, 2), nullable=True), schema=SCHEMA)
    op.add_column(
        "lot_prices",
        sa.Column("cap_du_per_acre_net", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.add_column("lot_prices", sa.Column("net_area_sqft", sa.Numeric(14, 2), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("lot_prices", "net_area_sqft", schema=SCHEMA)
    op.drop_column("lot_prices", "cap_du_per_acre_net", schema=SCHEMA)
    op.drop_column("lot_prices", "cap_max_units", schema=SCHEMA)
