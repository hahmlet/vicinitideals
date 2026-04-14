"""Add property fields to buildings table + opportunity_buildings join table

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add property data fields to buildings
    op.add_column("buildings", sa.Column("address_line1", sa.String(255), nullable=True))
    op.add_column("buildings", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("buildings", sa.Column("state", sa.String(2), nullable=True))
    op.add_column("buildings", sa.Column("zip_code", sa.String(10), nullable=True))
    op.add_column("buildings", sa.Column("unit_count", sa.Integer(), nullable=True))
    op.add_column("buildings", sa.Column("building_sqft", sa.Numeric(18, 2), nullable=True))
    op.add_column("buildings", sa.Column("lot_sqft", sa.Numeric(18, 2), nullable=True))
    op.add_column("buildings", sa.Column("year_built", sa.Integer(), nullable=True))
    op.add_column("buildings", sa.Column("stories", sa.Integer(), nullable=True))
    op.add_column("buildings", sa.Column("property_type", sa.String(100), nullable=True))
    op.add_column("buildings", sa.Column("current_use", sa.String(100), nullable=True))
    op.add_column("buildings", sa.Column("asking_price", sa.Numeric(18, 2), nullable=True))
    op.add_column("buildings", sa.Column("asking_cap_rate_pct", sa.Numeric(8, 4), nullable=True))
    op.add_column("buildings", sa.Column("status", sa.String(20), nullable=False, server_default="existing"))
    op.add_column("buildings", sa.Column("notes", sa.Text(), nullable=True))

    # Opportunity → Buildings join table
    op.create_table(
        "opportunity_buildings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", UUID(as_uuid=True),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("building_id", UUID(as_uuid=True),
                  sa.ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("role", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_opportunity_buildings_opportunity_id", "opportunity_buildings", ["opportunity_id"])
    op.create_index("ix_opportunity_buildings_building_id", "opportunity_buildings", ["building_id"])


def downgrade() -> None:
    op.drop_index("ix_opportunity_buildings_building_id", "opportunity_buildings")
    op.drop_index("ix_opportunity_buildings_opportunity_id", "opportunity_buildings")
    op.drop_table("opportunity_buildings")

    for col in ("notes", "status", "asking_cap_rate_pct", "asking_price", "current_use",
                "property_type", "stories", "year_built", "lot_sqft", "building_sqft",
                "unit_count", "zip_code", "state", "city", "address_line1"):
        op.drop_column("buildings", col)
