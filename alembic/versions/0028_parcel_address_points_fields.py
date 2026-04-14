"""Add Oregon Address Points fields to parcels table.

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
    op.add_column("parcels", sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
    op.add_column("parcels", sa.Column("postal_city", sa.String(120), nullable=True))
    op.add_column("parcels", sa.Column("zip_code", sa.String(20), nullable=True))
    op.add_column("parcels", sa.Column("unincorporated_community", sa.String(120), nullable=True))
    op.add_column("parcels", sa.Column("neighborhood", sa.String(120), nullable=True))
    op.add_column("parcels", sa.Column("address_unit", sa.String(100), nullable=True))
    op.add_column("parcels", sa.Column("building_id", sa.String(100), nullable=True))
    op.add_column("parcels", sa.Column("street_full_name", sa.String(255), nullable=True))
    op.add_column("parcels", sa.Column("street_number", sa.Integer, nullable=True))
    op.add_column("parcels", sa.Column("is_residential", sa.Boolean, nullable=True))
    op.add_column("parcels", sa.Column("is_mailable", sa.Boolean, nullable=True))
    op.add_column("parcels", sa.Column("address_stage", sa.String(50), nullable=True))
    op.add_column("parcels", sa.Column("place_type", sa.String(100), nullable=True))
    op.add_column("parcels", sa.Column("landmark_name", sa.String(255), nullable=True))
    op.add_column("parcels", sa.Column("address_placement", sa.String(50), nullable=True))
    op.add_column("parcels", sa.Column("elevation_ft", sa.Integer, nullable=True))
    op.add_column("parcels", sa.Column("address_source_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("parcels", sa.Column("address_effective_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("parcels", sa.Column("address_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("parcels", sa.Column("nguid", sa.String(200), nullable=True))
    op.add_column("parcels", sa.Column("discrepancy_agency_id", sa.String(200), nullable=True))
    op.add_column("parcels", sa.Column("esn", sa.String(50), nullable=True))
    op.add_column("parcels", sa.Column("msag_community", sa.String(120), nullable=True))

    op.create_index("ix_parcels_zip_code", "parcels", ["zip_code"])
    op.create_index("ix_parcels_postal_city", "parcels", ["postal_city"])
    op.create_index("ix_parcels_nguid", "parcels", ["nguid"], unique=True, postgresql_where=sa.text("nguid IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_parcels_nguid", "parcels")
    op.drop_index("ix_parcels_postal_city", "parcels")
    op.drop_index("ix_parcels_zip_code", "parcels")

    for col in [
        "latitude", "longitude", "postal_city", "zip_code",
        "unincorporated_community", "neighborhood", "address_unit", "building_id",
        "street_full_name", "street_number", "is_residential", "is_mailable",
        "address_stage", "place_type", "landmark_name", "address_placement",
        "elevation_ft", "address_source_updated_at", "address_effective_at",
        "address_expires_at", "nguid", "discrepancy_agency_id", "esn", "msag_community",
    ]:
        op.drop_column("parcels", col)
