"""REAL-61 scraped listing, property, and broker schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-03 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brokerages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("crexi_name", sa.Text(), nullable=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("street2", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("state_code", sa.Text(), nullable=True),
        sa.Column("zip_code", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "brokers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crexi_broker_id", sa.Integer(), nullable=True),
        sa.Column("crexi_global_id", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=True),
        sa.Column("last_name", sa.String(length=120), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("is_platinum", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("number_of_assets", sa.Integer(), nullable=True),
        sa.Column("brokerage_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("license_number", sa.String(length=100), nullable=True),
        sa.Column("license_state", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["brokerage_id"], ["brokerages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("crexi_broker_id"),
    )

    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scraped_listing_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"]),
        sa.ForeignKeyConstraint(["scraped_listing_id"], ["scraped_listings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scraped_listing_id"),
    )

    op.drop_constraint("scraped_listings_listing_url_key", "scraped_listings", type_="unique")

    op.add_column("scraped_listings", sa.Column("source_id", sa.String(length=255), nullable=True))
    op.add_column("scraped_listings", sa.Column("street", sa.Text(), nullable=True))
    op.add_column("scraped_listings", sa.Column("street2", sa.Text(), nullable=True))
    op.add_column("scraped_listings", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("county", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("state_code", sa.String(length=20), nullable=True))
    op.add_column("scraped_listings", sa.Column("zip_code", sa.String(length=20), nullable=True))
    op.add_column("scraped_listings", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("scraped_listings", sa.Column("lng", sa.Numeric(10, 7), nullable=True))
    op.add_column("scraped_listings", sa.Column("property_type", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("sub_type", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column("scraped_listings", sa.Column("investment_type", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("investment_sub_type", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("price_per_sqft", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("price_per_unit", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("price_per_sqft_land", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("net_rentable_sqft", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("year_renovated", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("buildings", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("stories", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("parking_spaces", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("pads", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("number_of_keys", sa.Integer(), nullable=True))
    op.add_column("scraped_listings", sa.Column("class_", sa.String(length=20), nullable=True))
    op.add_column("scraped_listings", sa.Column("zoning", sa.Text(), nullable=True))
    op.add_column("scraped_listings", sa.Column("apn", sa.String(length=100), nullable=True))
    op.add_column("scraped_listings", sa.Column("occupancy_pct", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("occupancy_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("tenancy", sa.String(length=50), nullable=True))
    op.add_column("scraped_listings", sa.Column("proforma_cap_rate", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("noi", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("proforma_noi", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("lease_term", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("lease_commencement", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("lease_expiration", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("remaining_term", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("rent_bumps", sa.Text(), nullable=True))
    op.add_column("scraped_listings", sa.Column("sale_condition", sa.Text(), nullable=True))
    op.add_column(
        "scraped_listings",
        sa.Column("broker_co_op", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("scraped_listings", sa.Column("ownership", sa.String(length=120), nullable=True))
    op.add_column("scraped_listings", sa.Column("is_in_opportunity_zone", sa.Boolean(), nullable=True))
    op.add_column("scraped_listings", sa.Column("listing_name", sa.String(length=255), nullable=True))
    op.add_column("scraped_listings", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("scraped_listings", sa.Column("parsed_description", sa.JSON(), nullable=True))
    op.add_column("scraped_listings", sa.Column("status", sa.String(length=100), nullable=True))
    op.add_column("scraped_listings", sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("broker_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("scraped_listings", sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE scraped_listings
            SET source_id = COALESCE(NULLIF(source_id, ''), NULLIF(listing_url, ''), CAST(id AS text))
            """
        )
    )
    op.alter_column("scraped_listings", "source_id", nullable=False)

    op.create_unique_constraint(
        "uq_scraped_listings_source_source_id",
        "scraped_listings",
        ["source", "source_id"],
    )
    op.create_index("ix_scraped_listings_apn", "scraped_listings", ["apn"], unique=False)
    op.create_index("ix_scraped_listings_property_type", "scraped_listings", ["property_type"], unique=False)

    op.create_foreign_key(
        "fk_scraped_listings_broker_id_brokers",
        "scraped_listings",
        "brokers",
        ["broker_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_scraped_listings_parcel_id_parcels",
        "scraped_listings",
        "parcels",
        ["parcel_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_scraped_listings_property_id_properties",
        "scraped_listings",
        "properties",
        ["property_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_scraped_listings_property_id_properties", "scraped_listings", type_="foreignkey")
    op.drop_constraint("fk_scraped_listings_parcel_id_parcels", "scraped_listings", type_="foreignkey")
    op.drop_constraint("fk_scraped_listings_broker_id_brokers", "scraped_listings", type_="foreignkey")
    op.drop_index("ix_scraped_listings_property_type", table_name="scraped_listings")
    op.drop_index("ix_scraped_listings_apn", table_name="scraped_listings")
    op.drop_constraint("uq_scraped_listings_source_source_id", "scraped_listings", type_="unique")
    op.create_unique_constraint("scraped_listings_listing_url_key", "scraped_listings", ["listing_url"])

    for column_name in [
        "property_id",
        "parcel_id",
        "broker_id",
        "updated_at_source",
        "listed_at",
        "status",
        "parsed_description",
        "description",
        "listing_name",
        "is_in_opportunity_zone",
        "ownership",
        "broker_co_op",
        "sale_condition",
        "rent_bumps",
        "remaining_term",
        "lease_expiration",
        "lease_commencement",
        "lease_term",
        "proforma_noi",
        "noi",
        "proforma_cap_rate",
        "tenancy",
        "occupancy_date",
        "occupancy_pct",
        "apn",
        "zoning",
        "class_",
        "number_of_keys",
        "pads",
        "parking_spaces",
        "stories",
        "buildings",
        "year_renovated",
        "net_rentable_sqft",
        "price_per_sqft_land",
        "price_per_unit",
        "price_per_sqft",
        "investment_sub_type",
        "investment_type",
        "sub_type",
        "property_type",
        "lng",
        "lat",
        "zip_code",
        "state_code",
        "county",
        "city",
        "street2",
        "street",
        "source_id",
    ]:
        op.drop_column("scraped_listings", column_name)

    op.drop_table("properties")
    op.drop_table("brokers")
    op.drop_table("brokerages")
