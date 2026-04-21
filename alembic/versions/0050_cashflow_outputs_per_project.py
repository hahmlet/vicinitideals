"""Add project_id to cashflow output tables so the engine can loop per project.

Phase 1 (migration 0048) added ``project_id`` to ``waterfall_tiers``,
``waterfall_results``, ``draw_sources`` but not the cashflow output tables
(``cash_flows``, ``cash_flow_line_items``, ``operational_outputs``). Phase 2
refactors ``compute_cash_flows`` to iterate projects — each project writes
its own rows — so those output tables need the column too.

All new columns are nullable FKs with CASCADE. Backfill points every
existing row at its scenario's oldest project (the current "default
project"). After backfill, for every row ``project_id`` is non-null.

The columns stay nullable in the schema to keep this migration reversible
and to avoid breaking the SQLite test fixture (which builds tables from
``Base.metadata.create_all()`` and does not run this migration).

Revision ID: 0050
Revises: 0049
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cash_flows",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_cash_flows_project", "cash_flows", ["project_id"])

    op.add_column(
        "cash_flow_line_items",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cash_flow_line_items_project", "cash_flow_line_items", ["project_id"]
    )

    op.add_column(
        "operational_outputs",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_operational_outputs_project", "operational_outputs", ["project_id"]
    )

    # Backfill: each scenario's oldest project is its "default project".
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for tbl in ("cash_flows", "cash_flow_line_items", "operational_outputs"):
            op.execute(
                f"""
                UPDATE {tbl} t SET project_id = (
                    SELECT p.id FROM projects p
                    WHERE p.scenario_id = t.scenario_id
                    ORDER BY p.created_at ASC LIMIT 1
                )
                WHERE project_id IS NULL
                """
            )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_outputs_project", table_name="operational_outputs"
    )
    op.drop_column("operational_outputs", "project_id")

    op.drop_index(
        "ix_cash_flow_line_items_project", table_name="cash_flow_line_items"
    )
    op.drop_column("cash_flow_line_items", "project_id")

    op.drop_index("ix_cash_flows_project", table_name="cash_flows")
    op.drop_column("cash_flows", "project_id")
