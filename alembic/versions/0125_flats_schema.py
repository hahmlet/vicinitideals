"""Create the ``flats`` schema and its seven tables.

A dedicated Postgres schema, not a table prefix. FLATS and the underwriting
platform share this database; keeping them in separate namespaces makes the
product boundary structural rather than a convention, and means a query against
``public`` can never reach screening data by accident.

The keying is the part that had to be right now, because it is the part that is
expensive to change later: results are ``(lot, design, run)`` from the first row,
so adding a second building design is a re-run rather than a migration; and
review decisions key on the durable taxlot id rather than a lot row id, so a
human verdict survives the pipeline rebuilding ``flats.lots`` underneath it.

Column sets that are still open — the per-lot computed facts, the per-check
detail — are JSONB rather than guessed columns, because the stages that will
fill them are not written yet and a guess would only buy a churn of migrations.

Empty on arrival. Nothing writes to these tables until the ingest and scoring
stages land; this ships now so that when they do, the shape is already correct.

Revision ID: 0125
Revises: 0124
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None

SCHEMA = "flats"
SRID_WORKING = 2913  # NAD83(HARN) / Oregon North, feet — the CRS the code is written in
SRID_WGS84 = 4326


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("code_version", sa.String(length=64), nullable=True),
        sa.Column("rules_version", sa.String(length=64), nullable=True),
        sa.Column("design_keys", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("counties", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    op.create_table(
        "designs",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("design_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("typology", sa.String(length=48), nullable=False),
        sa.Column("width_ft", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("depth_ft", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("stories", sa.Integer(), nullable=False),
        sa.Column("height_ft", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("spec", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("design_id", "version", name="uq_flats_designs_id_version"),
        schema=SCHEMA,
    )

    op.create_table(
        "lots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tlid", sa.String(length=40), nullable=False),
        sa.Column("county", sa.String(length=40), nullable=False),
        sa.Column("jurisdiction", sa.String(length=80), nullable=False),
        sa.Column("zone_raw", sa.String(length=40), nullable=True),
        sa.Column("zone", sa.String(length=40), nullable=True),
        sa.Column("site_address", sa.String(length=255), nullable=True),
        sa.Column("area_sqft", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON", srid=SRID_WORKING, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column(
            "centroid",
            geoalchemy2.types.Geometry(
                geometry_type="POINT", srid=SRID_WGS84, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column("condo_verdict", sa.String(length=16), nullable=True),
        sa.Column("condo_reason", sa.String(length=48), nullable=True),
        sa.Column("facts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("first_seen_run_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_run_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["first_seen_run_id"], [f"{SCHEMA}.runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_run_id"], [f"{SCHEMA}.runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("county", "tlid", name="uq_flats_lots_county_tlid"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lots_jurisdiction_zone", "lots", ["jurisdiction", "zone"], schema=SCHEMA
    )
    op.create_index(
        "ix_flats_lots_geom", "lots", ["geom"], schema=SCHEMA, postgresql_using="gist"
    )
    op.create_index(
        "ix_flats_lots_centroid", "lots", ["centroid"], schema=SCHEMA, postgresql_using="gist"
    )

    op.create_table(
        "lot_results",
        sa.Column("lot_id", sa.BigInteger(), nullable=False),
        sa.Column("design_key", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(length=10), nullable=False),
        sa.Column("slack_ft", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("binding", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("checks", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "site_plan",
            geoalchemy2.types.Geometry(
                geometry_type="GEOMETRYCOLLECTION", srid=SRID_WORKING, spatial_index=False
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["lot_id"], [f"{SCHEMA}.lots.id"], ondelete="CASCADE"),
        # RESTRICT, not CASCADE: deleting a design must not silently delete the
        # results that explain what it unlocked.
        sa.ForeignKeyConstraint(["design_key"], [f"{SCHEMA}.designs.key"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], [f"{SCHEMA}.runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lot_id", "design_key", "run_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_results_run_tier", "lot_results", ["run_id", "tier"], schema=SCHEMA
    )
    op.create_index(
        "ix_flats_lot_results_design_tier", "lot_results", ["design_key", "tier"], schema=SCHEMA
    )

    op.create_table(
        "rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=80), nullable=False),
        sa.Column("zone", sa.String(length=40), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("layer", sa.String(length=80), nullable=True),
        sa.Column("preempted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cite", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("retrieved", sa.Date(), nullable=True),
        sa.Column("reviewer", sa.String(length=80), nullable=True),
        sa.Column("reviewed", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], [f"{SCHEMA}.runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "jurisdiction", "zone", "field", name="uq_flats_rules_run_zone_field"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "clauses",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("jurisdiction", sa.String(length=80), nullable=False),
        sa.Column("section", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tag", sa.String(length=1), nullable=True),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("reviewer", sa.String(length=80), nullable=True),
        sa.Column("reviewed", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_clauses_jurisdiction_section", "clauses", ["jurisdiction", "section"], schema=SCHEMA
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("county", sa.String(length=40), nullable=False),
        sa.Column("tlid", sa.String(length=40), nullable=False),
        # Empty string rather than NULL: NULLs drop out of the partial unique
        # index below, which would let duplicate active decisions accumulate on
        # exactly the design-independent verdicts the index exists to protect.
        sa.Column("design_key", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("check_code", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["public.organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    # One live decision per (lot, design, check); superseded rows stay for history.
    op.create_index(
        "uq_flats_review_active",
        "review_decisions",
        ["county", "tlid", "design_key", "check_code"],
        schema=SCHEMA,
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    # CASCADE on the schema drop: the tables are empty until the ingest stage
    # lands, and dropping them individually would only fight the FK ordering.
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
