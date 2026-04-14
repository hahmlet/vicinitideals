"""Add enterprise_zone_name to parcels table.

Stores the name of the enterprise zone a parcel falls within (e.g. "Columbia
Cascade Enterprise Zone"). NULL means not in any EZ. Populated by spatial join
against the enterprise_zones_or cached polygon layer at seed time — covers all
jurisdictions including Fairview automatically via the statewide Business Oregon
layer, supplemented by Fairview's own FeatureServer
(Enterprise_Zones_201806_FVR/FeatureServer/6).

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("enterprise_zone_name", sa.String(120), nullable=True))
    op.create_index("ix_parcels_enterprise_zone_name", "parcels", ["enterprise_zone_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_parcels_enterprise_zone_name", table_name="parcels")
    op.drop_column("parcels", "enterprise_zone_name")
