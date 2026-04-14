"""Refactor entity renames — Phase 1b

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-04

Creates the new projects table (post-acquisition development effort) and
re-keys line-item tables from deal_id / deal_model_id → project_id.

Changes:
  1. Create projects table (id, deal_id→deals, opportunity_id→opportunities, deal_type, name)
  2. Seed one default Project per existing Deal (opportunity_id + deal_type copied from Deal)
  3. Add project_id (nullable) to: use_lines, income_streams,
     operating_expense_lines, operational_inputs
  4. Backfill project_id from the seeded projects
  5. Alter project_id → NOT NULL
  6. Drop old deal_id from use_lines
     Drop old deal_model_id from income_streams, operating_expense_lines, operational_inputs

  NOTE: deals.project_type is kept as-is for now (Phase 2 Python model refactor
  will drop it from Deal and keep it only on Project).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Create projects table
    # -------------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deal_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("deals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default="Default Project"),
        sa.Column("deal_type", sa.String(60), nullable=False, server_default="acquisition_major_reno"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_projects_deal_id", "projects", ["deal_id"])
    op.create_index("ix_projects_opportunity_id", "projects", ["opportunity_id"])

    # -------------------------------------------------------------------------
    # 2. Seed one default Project per existing Deal
    #    Copies opportunity_id + project_type from deals row.
    # -------------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO projects (id, deal_id, opportunity_id, name, deal_type)
        SELECT
            gen_random_uuid(),
            d.id,
            d.opportunity_id,
            'Default Project',
            COALESCE(d.project_type, 'acquisition_major_reno')
        FROM deals d
        """
    )

    # -------------------------------------------------------------------------
    # 3a. use_lines: add project_id (nullable), backfill, NOT NULL, drop deal_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE use_lines ul
        SET project_id = p.id
        FROM projects p
        WHERE ul.deal_id = p.deal_id
        """
    )

    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.alter_column("project_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_use_lines_project_id", "projects", ["project_id"], ["id"]
        )
        batch_op.drop_column("deal_id")

    op.create_index("ix_use_lines_project_id", "use_lines", ["project_id"])

    # -------------------------------------------------------------------------
    # 3b. income_streams: add project_id, backfill from deal_model_id, drop old col
    # -------------------------------------------------------------------------
    with op.batch_alter_table("income_streams") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE income_streams s
        SET project_id = p.id
        FROM projects p
        WHERE s.deal_model_id = p.deal_id
        """
    )

    with op.batch_alter_table("income_streams") as batch_op:
        batch_op.alter_column("project_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_income_streams_project_id", "projects", ["project_id"], ["id"]
        )
        batch_op.drop_column("deal_model_id")

    op.create_index("ix_income_streams_project_id", "income_streams", ["project_id"])

    # -------------------------------------------------------------------------
    # 3c. operating_expense_lines: add project_id, backfill, drop old col
    # -------------------------------------------------------------------------
    with op.batch_alter_table("operating_expense_lines") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE operating_expense_lines e
        SET project_id = p.id
        FROM projects p
        WHERE e.deal_model_id = p.deal_id
        """
    )

    with op.batch_alter_table("operating_expense_lines") as batch_op:
        batch_op.alter_column("project_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_operating_expense_lines_project_id", "projects", ["project_id"], ["id"]
        )
        batch_op.drop_column("deal_model_id")

    op.create_index(
        "ix_operating_expense_lines_project_id", "operating_expense_lines", ["project_id"]
    )

    # -------------------------------------------------------------------------
    # 3d. operational_inputs: add project_id, backfill, drop old col
    #     (unique constraint moves to project_id — 1:1 with Project)
    # -------------------------------------------------------------------------
    with op.batch_alter_table("operational_inputs") as batch_op:
        batch_op.add_column(
            sa.Column("project_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE operational_inputs i
        SET project_id = p.id
        FROM projects p
        WHERE i.deal_model_id = p.deal_id
        """
    )

    with op.batch_alter_table("operational_inputs") as batch_op:
        batch_op.alter_column("project_id", nullable=False)
        batch_op.create_unique_constraint("uq_operational_inputs_project_id", ["project_id"])
        batch_op.create_foreign_key(
            "fk_operational_inputs_project_id", "projects", ["project_id"], ["id"]
        )
        batch_op.drop_column("deal_model_id")


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # Restore operational_inputs.deal_model_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("operational_inputs") as batch_op:
        batch_op.add_column(
            sa.Column("deal_model_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE operational_inputs i
        SET deal_model_id = p.deal_id
        FROM projects p
        WHERE i.project_id = p.id
        """
    )

    with op.batch_alter_table("operational_inputs") as batch_op:
        batch_op.drop_constraint("fk_operational_inputs_project_id", type_="foreignkey")
        batch_op.drop_constraint("uq_operational_inputs_project_id", type_="unique")
        batch_op.alter_column("deal_model_id", nullable=False)
        batch_op.drop_column("project_id")

    # -------------------------------------------------------------------------
    # Restore operating_expense_lines.deal_model_id
    # -------------------------------------------------------------------------
    op.drop_index("ix_operating_expense_lines_project_id", "operating_expense_lines")

    with op.batch_alter_table("operating_expense_lines") as batch_op:
        batch_op.add_column(
            sa.Column("deal_model_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE operating_expense_lines e
        SET deal_model_id = p.deal_id
        FROM projects p
        WHERE e.project_id = p.id
        """
    )

    with op.batch_alter_table("operating_expense_lines") as batch_op:
        batch_op.drop_constraint("fk_operating_expense_lines_project_id", type_="foreignkey")
        batch_op.alter_column("deal_model_id", nullable=False)
        batch_op.drop_column("project_id")

    # -------------------------------------------------------------------------
    # Restore income_streams.deal_model_id
    # -------------------------------------------------------------------------
    op.drop_index("ix_income_streams_project_id", "income_streams")

    with op.batch_alter_table("income_streams") as batch_op:
        batch_op.add_column(
            sa.Column("deal_model_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE income_streams s
        SET deal_model_id = p.deal_id
        FROM projects p
        WHERE s.project_id = p.id
        """
    )

    with op.batch_alter_table("income_streams") as batch_op:
        batch_op.drop_constraint("fk_income_streams_project_id", type_="foreignkey")
        batch_op.alter_column("deal_model_id", nullable=False)
        batch_op.drop_column("project_id")

    # -------------------------------------------------------------------------
    # Restore use_lines.deal_id
    # -------------------------------------------------------------------------
    op.drop_index("ix_use_lines_project_id", "use_lines")

    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.add_column(
            sa.Column("deal_id", PG_UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        """
        UPDATE use_lines ul
        SET deal_id = p.deal_id
        FROM projects p
        WHERE ul.project_id = p.id
        """
    )

    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.drop_constraint("fk_use_lines_project_id", type_="foreignkey")
        batch_op.alter_column("deal_id", nullable=False)
        batch_op.drop_column("project_id")

    # -------------------------------------------------------------------------
    # Drop seeded projects + projects table
    # -------------------------------------------------------------------------
    op.drop_index("ix_projects_opportunity_id", "projects")
    op.drop_index("ix_projects_deal_id", "projects")
    op.drop_table("projects")
