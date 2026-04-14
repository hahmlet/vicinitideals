"""Add milestone_key to use_lines, populate from phase.

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

_PHASE_TO_MILESTONE = {
    "acquisition": "close",
    "pre_construction": "pre_development",
    "construction": "construction",
    "renovation": "construction",
    "conversion": "construction",
    "operation": "operation_stabilized",
    "exit": "divestment",
    "other": "close",
}


def upgrade() -> None:
    op.add_column("use_lines", sa.Column(
        "milestone_key", sa.String(60), nullable=True
    ))
    # Populate from existing phase values
    conn = op.get_bind()
    for phase, ms_key in _PHASE_TO_MILESTONE.items():
        conn.execute(
            sa.text(
                "UPDATE use_lines SET milestone_key = :ms WHERE phase = :phase"
            ),
            {"ms": ms_key, "phase": phase},
        )


def downgrade() -> None:
    op.drop_column("use_lines", "milestone_key")
