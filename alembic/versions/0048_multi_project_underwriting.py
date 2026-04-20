"""Multi-project underwriting — foundation schema.

Adds the data structures needed for one Scenario to carry N Projects with
per-project capital-source terms and cross-project timelines. No engine or UI
changes in this migration — existing single-project scenarios keep producing
byte-identical output because the engine still treats the first project as the
default and the new junction gets a 1:1 backfill.

New tables:
  - capital_module_projects: per-project terms for each CapitalModule.
      One row per (module, project) pair. N > 1 rows = shared source.
      Carries per-project amount, active window (milestone keys + day
      offsets), and auto_size flag.
  - project_anchors: cross-project timeline coupling. If a row exists for
      project P, P's first-milestone date resolves relative to the anchor
      project's anchor_milestone plus offset_months + offset_days. Absence =
      project uses its own start_date as today.

New columns:
  - use_lines.source_capital_module_id   — nullable FK. Engine-injected
      reserves (IR / CI / Acq Interest / Lease-Up Reserve) will tag the
      originating CapitalModule so rollups can sum reserves per source.
  - waterfall_tiers.project_id           — nullable FK. Waterfall becomes
      per-project; joined table at Underwriting layer concatenates rows.
  - waterfall_results.project_id         — same.
  - draw_sources.project_id              — same.

Backfill: every existing CapitalModule / WaterfallTier / WaterfallResult /
DrawSource is linked to its scenario's first project (ordered by created_at).
Since in practice every scenario has exactly one project today, this is a
1:1 mapping and preserves all existing math.

Revision ID: 0048
Revises: 0047
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── capital_module_projects junction ──────────────────────────────────
    op.create_table(
        "capital_module_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "capital_module_id",
            UUID(as_uuid=True),
            sa.ForeignKey("capital_modules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("active_from", sa.String(60), nullable=True),
        sa.Column("active_to", sa.String(60), nullable=True),
        sa.Column("active_from_offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_to_offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_size", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "capital_module_id", "project_id", name="uq_capital_module_project"
        ),
    )
    op.create_index(
        "ix_capital_module_projects_module",
        "capital_module_projects",
        ["capital_module_id"],
    )
    op.create_index(
        "ix_capital_module_projects_project",
        "capital_module_projects",
        ["project_id"],
    )

    # ── project_anchors: cross-project timeline coupling ──────────────────
    op.create_table(
        "project_anchors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "anchor_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "anchor_milestone_id",
            UUID(as_uuid=True),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("offset_months", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_project_anchors_anchor_project",
        "project_anchors",
        ["anchor_project_id"],
    )

    # ── per-project FKs on waterfall / draws / use-line reserves ──────────
    op.add_column(
        "use_lines",
        sa.Column(
            "source_capital_module_id",
            UUID(as_uuid=True),
            sa.ForeignKey("capital_modules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_use_lines_source_capital_module",
        "use_lines",
        ["source_capital_module_id"],
    )

    op.add_column(
        "waterfall_tiers",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_waterfall_tiers_project", "waterfall_tiers", ["project_id"])

    op.add_column(
        "waterfall_results",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_waterfall_results_project", "waterfall_results", ["project_id"])

    op.add_column(
        "draw_sources",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_draw_sources_project", "draw_sources", ["project_id"])

    # ── backfills ─────────────────────────────────────────────────────────
    # Pick each scenario's default project: the oldest project by created_at.
    # Works on Postgres and SQLite (tests). DISTINCT ON would be faster on PG
    # but DISTINCT ON is Postgres-only; a correlated subquery is portable.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # capital_module_projects: one row per (module, default project) with
        # amount / window / auto_size lifted from the module's JSON + legacy
        # columns. gen_random_uuid() comes from pgcrypto; scenarios already
        # rely on it.
        op.execute(
            """
            INSERT INTO capital_module_projects
                (id, capital_module_id, project_id, amount,
                 active_from, active_to,
                 active_from_offset_days, active_to_offset_days,
                 auto_size, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                cm.id,
                (SELECT p.id FROM projects p
                 WHERE p.scenario_id = cm.scenario_id
                 ORDER BY p.created_at ASC LIMIT 1),
                COALESCE((cm.source->>'amount')::numeric, 0),
                cm.active_phase_start,
                cm.active_phase_end,
                0,
                0,
                COALESCE((cm.source->>'auto_size')::boolean, false),
                now(),
                now()
            FROM capital_modules cm
            WHERE EXISTS (
                SELECT 1 FROM projects p WHERE p.scenario_id = cm.scenario_id
            )
            """
        )

        op.execute(
            """
            UPDATE waterfall_tiers wt SET project_id = (
                SELECT p.id FROM projects p
                WHERE p.scenario_id = wt.scenario_id
                ORDER BY p.created_at ASC LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
        op.execute(
            """
            UPDATE waterfall_results wr SET project_id = (
                SELECT p.id FROM projects p
                WHERE p.scenario_id = wr.scenario_id
                ORDER BY p.created_at ASC LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
        op.execute(
            """
            UPDATE draw_sources ds SET project_id = (
                SELECT p.id FROM projects p
                WHERE p.scenario_id = ds.scenario_id
                ORDER BY p.created_at ASC LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
    # SQLite (test runtime): the fixtures create scenarios with zero pre-
    # existing capital modules / waterfall rows, so there is nothing to
    # backfill. Skip the DML entirely — it relies on JSON operators and
    # gen_random_uuid() which SQLite lacks.


def downgrade() -> None:
    op.drop_index("ix_draw_sources_project", table_name="draw_sources")
    op.drop_column("draw_sources", "project_id")

    op.drop_index("ix_waterfall_results_project", table_name="waterfall_results")
    op.drop_column("waterfall_results", "project_id")

    op.drop_index("ix_waterfall_tiers_project", table_name="waterfall_tiers")
    op.drop_column("waterfall_tiers", "project_id")

    op.drop_index("ix_use_lines_source_capital_module", table_name="use_lines")
    op.drop_column("use_lines", "source_capital_module_id")

    op.drop_index("ix_project_anchors_anchor_project", table_name="project_anchors")
    op.drop_table("project_anchors")

    op.drop_index(
        "ix_capital_module_projects_project", table_name="capital_module_projects"
    )
    op.drop_index(
        "ix_capital_module_projects_module", table_name="capital_module_projects"
    )
    op.drop_table("capital_module_projects")
