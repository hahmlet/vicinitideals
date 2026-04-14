"""Add indexes on parcels for filter columns (jurisdiction, gis_acres, year_built, zoning_code).

Revision ID: 0033
Revises: 0032
Create Date: 2026-04-12
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_parcels_jurisdiction", "parcels", ["jurisdiction"])
    op.create_index("ix_parcels_zoning_code", "parcels", ["zoning_code"])
    op.create_index("ix_parcels_gis_acres", "parcels", ["gis_acres"])
    op.create_index("ix_parcels_year_built", "parcels", ["year_built"])


def downgrade() -> None:
    op.drop_index("ix_parcels_year_built", table_name="parcels")
    op.drop_index("ix_parcels_gis_acres", table_name="parcels")
    op.drop_index("ix_parcels_zoning_code", table_name="parcels")
    op.drop_index("ix_parcels_jurisdiction", table_name="parcels")
