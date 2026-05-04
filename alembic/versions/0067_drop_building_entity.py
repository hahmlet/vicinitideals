"""Drop Building entity; rename scraped_listings → opportunities.

Decision: no separate buildings table. Physical attributes live as nullable columns
directly on the new opportunities table (renamed from scraped_listings). Parcel is
the authoritative seed; opportunity columns are permanent override when non-null.

Data purge approved in refactor plan — all deal/scenario/project rows are wiped.
Parcels and scraped listings (now opportunities) are preserved.

Revision ID: 0067
Revises: 0066
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. PURGE deal/project data (reverse FK order) ─────────────────────
    for tbl in [
        "cash_flow_line_items",
        "cash_flows",
        "operational_outputs",
        "waterfall_results",
        "use_lines",
        "income_streams",
        "operating_expense_lines",
        "unit_mix",
        "draw_sources",
        "capital_module_projects",
        "capital_modules",
        "waterfall_tiers",
        "project_anchors",
        "project_building_assignments",
        "project_parcel_assignments",
        "milestones",
        "projects",
        "operational_inputs",
        "scenarios",
        "deal_opportunities",
        "deals",
        "opportunity_buildings",
        "parcel_transformations",
        "permit_stubs",
        "workflow_run_manifests",
    ]:
        conn.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608

    # Null out FK columns in kept tables that reference old opportunities
    conn.execute(text("UPDATE project_visibilities SET opportunity_id = NULL"))
    conn.execute(text("UPDATE sensitivities SET opportunity_id = NULL"))
    conn.execute(text("UPDATE portfolio_projects SET opportunity_id = NULL"))
    conn.execute(text("UPDATE gantt_entries SET opportunity_id = NULL"))

    # ── 2. DROP building/junction tables (CASCADE removes FK constraints) ──
    for tbl in [
        "project_building_assignments",
        "opportunity_buildings",
        "project_parcel_assignments",
        "project_parcels",
        "deal_opportunities",
        "buildings",
    ]:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))  # noqa: S608

    # ── 3. DROP old opportunities table (CASCADE removes FK constraints
    #        from milestones, permit_stubs, parcel_transformations,
    #        project_visibilities, sensitivities, portfolio_projects,
    #        gantt_entries, projects, scraped_listings.linked_project_id) ──
    conn.execute(text("DROP TABLE IF EXISTS opportunities CASCADE"))

    # ── 4. Drop stale columns from scraped_listings (FKs gone via CASCADE) ─
    conn.execute(text("ALTER TABLE scraped_listings DROP COLUMN IF EXISTS property_id"))
    conn.execute(text("ALTER TABLE scraped_listings DROP COLUMN IF EXISTS linked_project_id"))

    # ── 5. Rename scraped_listings → opportunities ─────────────────────────
    conn.execute(text("ALTER TABLE scraped_listings RENAME TO opportunities"))

    # ── 6. Add org-metadata columns to new opportunities ──────────────────
    conn.execute(text("""
        ALTER TABLE opportunities
            ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id),
            ADD COLUMN IF NOT EXISTS opp_status VARCHAR(50) DEFAULT 'hypothetical',
            ADD COLUMN IF NOT EXISTS project_category VARCHAR(50) DEFAULT 'proposed',
            ADD COLUMN IF NOT EXISTS name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS promotion_source VARCHAR(20),
            ADD COLUMN IF NOT EXISTS promotion_ruleset_id UUID
                REFERENCES saved_search_criteria(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id),
            ADD COLUMN IF NOT EXISTS notes TEXT
    """))

    # ── 7. Re-add FK constraints from kept tables → new opportunities ──────
    conn.execute(text("""
        ALTER TABLE milestones
            ADD CONSTRAINT fk_milestones_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))
    conn.execute(text("""
        ALTER TABLE parcel_transformations
            ADD CONSTRAINT fk_parcel_transformations_project_id
            FOREIGN KEY (project_id) REFERENCES opportunities(id) ON DELETE CASCADE
    """))
    conn.execute(text("""
        ALTER TABLE permit_stubs
            ADD CONSTRAINT fk_permit_stubs_project_id
            FOREIGN KEY (project_id) REFERENCES opportunities(id) ON DELETE CASCADE
    """))
    conn.execute(text("""
        ALTER TABLE project_visibilities
            ADD CONSTRAINT fk_project_visibilities_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))
    conn.execute(text("""
        ALTER TABLE sensitivities
            ADD CONSTRAINT fk_sensitivities_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))
    conn.execute(text("""
        ALTER TABLE portfolio_projects
            ADD CONSTRAINT fk_portfolio_projects_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))
    conn.execute(text("""
        ALTER TABLE gantt_entries
            ADD CONSTRAINT fk_gantt_entries_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))

    # ── 8. Modify projects table ──────────────────────────────────────────
    conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS deal_type"))
    conn.execute(text("""
        ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS proposed_use VARCHAR(60),
            ADD COLUMN IF NOT EXISTS acquisition_price NUMERIC(18, 2),
            ADD COLUMN IF NOT EXISTS parcel_id UUID REFERENCES parcels(id),
            ADD COLUMN IF NOT EXISTS unit_mix JSONB
    """))
    # Re-add FK from projects.opportunity_id to new opportunities
    conn.execute(text("""
        ALTER TABLE projects
            ADD CONSTRAINT fk_projects_opportunity_id
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
    """))

    # ── 9. Drop standalone unit_mix table (moved to JSONB on projects) ────
    conn.execute(text("DROP TABLE IF EXISTS unit_mix CASCADE"))


def downgrade() -> None:
    # Destructive purge + rename — not reversible.
    pass
