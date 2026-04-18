"""Replace legacy avg_monthly_rent with beds/baths variables on UnitMix.

The legacy `avg_monthly_rent` field is removed — it duplicated in_place_rent
semantically and created ambiguity. Beds and baths are added as first-class
numeric variables so comp-data ingestion can populate them directly:
  - beds: 0..5+ (whole numbers; 5 represents "5 or more")
  - baths: 0..3.5+ in 0.5 increments

This migration is NOT backward-compatible: any existing avg_monthly_rent
values are dropped. The user has accepted this.

Revision ID: 0046
Revises: 0045
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unit_mix", sa.Column("beds", sa.Numeric(4, 1), nullable=True))
    op.add_column("unit_mix", sa.Column("baths", sa.Numeric(4, 1), nullable=True))
    op.drop_column("unit_mix", "avg_monthly_rent")


def downgrade() -> None:
    op.add_column("unit_mix", sa.Column("avg_monthly_rent", sa.Numeric(18, 2), nullable=True))
    op.drop_column("unit_mix", "baths")
    op.drop_column("unit_mix", "beds")
