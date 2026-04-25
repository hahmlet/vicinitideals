"""Add loopnet_broker_id to brokers — alphanumeric slug from LoopNet broker URL.

LoopNet broker profile URLs follow the pattern:
  https://www.loopnet.com/commercial-real-estate-brokers/profile/{name-slug}/{broker-id}/{listing-id}#RealEstateAgent

The 5-12 char alphanumeric `broker-id` (e.g. "mzwstflb", "zxz0drxb") is what
the /loopnet/broker/extendedDetails endpoint accepts. Persisting it lets us:

  - Link multiple LoopNet listings to the same Broker row (one broker covers
    many listings, just like crexi_broker_id today)
  - Avoid re-fetching broker bio/specialties on every listing pull
  - Cross-reference with future LoopNet broker-search/list endpoints

Revision ID: 0059
Revises: 0058
Create Date: 2026-04-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brokers",
        sa.Column("loopnet_broker_id", sa.String(40), nullable=True),
    )
    # Unique on populated values only (allows many NULLs from Crexi-only brokers)
    op.create_index(
        "ix_brokers_loopnet_broker_id",
        "brokers",
        ["loopnet_broker_id"],
        unique=True,
        postgresql_where=sa.text("loopnet_broker_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_brokers_loopnet_broker_id", table_name="brokers")
    op.drop_column("brokers", "loopnet_broker_id")
