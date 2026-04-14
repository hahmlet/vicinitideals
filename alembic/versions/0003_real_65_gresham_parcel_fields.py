"""REAL-65 Gresham parcel enrichment fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03 00:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("state_id", sa.String(length=100), nullable=True))
    op.add_column("parcels", sa.Column("owner_street", sa.Text(), nullable=True))
    op.add_column("parcels", sa.Column("owner_city", sa.String(length=120), nullable=True))
    op.add_column("parcels", sa.Column("owner_state", sa.String(length=20), nullable=True))
    op.add_column("parcels", sa.Column("owner_zip", sa.String(length=20), nullable=True))
    op.add_column("parcels", sa.Column("gis_acres", sa.Numeric(18, 8), nullable=True))
    op.add_column("parcels", sa.Column("total_assessed_value", sa.Numeric(18, 6), nullable=True))
    op.add_column("parcels", sa.Column("tax_code", sa.String(length=50), nullable=True))
    op.add_column("parcels", sa.Column("legal_description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("parcels", "legal_description")
    op.drop_column("parcels", "tax_code")
    op.drop_column("parcels", "total_assessed_value")
    op.drop_column("parcels", "gis_acres")
    op.drop_column("parcels", "owner_zip")
    op.drop_column("parcels", "owner_state")
    op.drop_column("parcels", "owner_city")
    op.drop_column("parcels", "owner_street")
    op.drop_column("parcels", "state_id")
