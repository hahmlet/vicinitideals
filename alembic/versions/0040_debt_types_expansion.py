"""Add debt_types and debt_milestone_config to operational_inputs; add FunderType enum values.

Revision ID: 0040
Revises: 0039
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, JSONB

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add debt_types: ordered list of funder_type strings for the multi-debt wizard
    op.add_column(
        "operational_inputs",
        sa.Column("debt_types", JSONB, nullable=True),
    )
    # Add debt_milestone_config: per-debt active_from / active_to / retired_by
    op.add_column(
        "operational_inputs",
        sa.Column("debt_milestone_config", JSONB, nullable=True),
    )

    # Backfill debt_types from existing debt_structure for old deals
    op.execute("""
        UPDATE operational_inputs
        SET debt_types = CASE debt_structure
            WHEN 'perm_only'             THEN '["permanent_debt"]'::jsonb
            WHEN 'construction_to_perm'  THEN '["construction_to_perm"]'::jsonb
            WHEN 'construction_and_perm' THEN '["construction_loan", "permanent_debt"]'::jsonb
            ELSE NULL
        END
        WHERE debt_structure IS NOT NULL AND debt_types IS NULL
    """)

    # Add new FunderType values to the PostgreSQL enum (if using native enum type)
    # Note: FunderType is a Python str enum stored as VARCHAR — no ALTER TYPE needed.
    # The new values (pre_development_loan, acquisition_loan) are valid once the
    # Python model is updated. No SQL enum change required.


def downgrade() -> None:
    op.drop_column("operational_inputs", "debt_milestone_config")
    op.drop_column("operational_inputs", "debt_types")
