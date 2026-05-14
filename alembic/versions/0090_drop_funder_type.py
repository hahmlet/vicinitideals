"""drop funder_type column from capital_modules and draw_sources

Revision ID: 0090
Revises: 0089
Create Date: 2026-05-14

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("capital_modules", "funder_type")
    op.drop_column("draw_sources", "funder_type")
    # Drop the PostgreSQL enum type that backed the funder_type column.
    op.execute("DROP TYPE IF EXISTS fundertype CASCADE")


def downgrade() -> None:
    # Non-trivial — funder_type was NOT NULL on capital_modules.
    # Downgrade intentionally left incomplete (would require data backfill).
    pass
